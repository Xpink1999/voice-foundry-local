"""Disk-streamed chapter/book assembly, review gates, RF64 and ZIP64 exports."""
import json
import subprocess
import time
import zipfile
from pathlib import Path
import numpy as np
import soundfile as sf
from .audio import sha256,safe_name,srt_time
from .store import now,uid
from .worker_runner import kill_worker
from .process_owner import ProcessOwner

def wav_container(frames):return 'RF64' if frames*3>4294967000 else 'WAV'

class LongformExport:
    def __init__(self,owner):self.owner=owner;self.db=owner.db;self.store=owner.store
    def submit(self,identity,request):
        with self.store.lock,self.store.connect() as db:
            book=self.db.book(identity);self.owner.book(identity)
            if book['segments']==0:raise ValueError('作品没有可导出的分段')
            if book['phase']!='ready':raise ValueError('文本尚未准备好')
            if book['state']=='running' or db.execute("SELECT 1 FROM lf_segments WHERE book_id=? AND status='running' LIMIT 1",(identity,)).fetchone():raise ValueError('请先暂停生成，等待当前段结束后导出')
            if db.execute("SELECT 1 FROM lf_exports WHERE book_id=? AND state IN ('queued','running','cancel_requested') LIMIT 1",(identity,)).fetchone():raise ValueError('本作品已有导出正在执行')
            where='book_id=? AND deleted_batch IS NULL AND segments>0';args=[identity]
            if request.chapter_no is not None:
                where+=' AND no=?';args.append(request.chapter_no)
                if not self.db.chapter(identity,request.chapter_no)['segments']:raise ValueError('本章没有可导出的分段')
            invalid=db.execute('SELECT 1 FROM lf_chapters WHERE '+where+' AND (done!=segments OR failed>0'+(')' if request.draft else " OR review!='approved' OR review_version!=revision)" )+' LIMIT 1',args).fetchone()
            if invalid:raise ValueError('所选章节尚未全部生成或未经当前版本的试听审核；试音请显式选择草稿导出')
            item=dict(id=uid(),book_id=identity,request=request.model_dump(),state='queued',progress=0,message='等待分块导出',created_at=now(),error=None,book_title=book['title'])
            self.db.save_export(item);self.owner.wake.set();return item
    def check(self,identity):
        if self.owner.stop_event.is_set():raise InterruptedError('服务停止，已写文件保留，请重新提交导出')
        if self.db.export(identity)['state']=='cancel_requested':raise InterruptedError('导出已取消，已写文件保留')
    def cancel(self,identity):
        item=self.db.export(identity)
        if item['state']=='queued':item['state']='cancelled'
        elif item['state']=='running':item['state']='cancel_requested'
        self.db.save_export(item);return item
    def loop(self):
        while not self.owner.stop_event.is_set():
            with self.store.connect() as db:row=db.execute("SELECT id FROM lf_exports WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:self.owner.wake.wait(.5);self.owner.wake.clear();continue
            with self.store.lock:
                item=self.db.export(row[0])
                if item['state']!='queued':continue
                item.update(state='running',message='校验音频并分块合成');self.db.save_export(item)
            try:self.run(item)
            except Exception as error:
                item.update(state='interrupted' if self.owner.stop_event.is_set() else 'cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error)[:2000],finished_at=now())
                self.db.save_export(item)
    def chapter_rows(self,book,chapter_no=None):
        cursor=0
        while True:
            with self.store.connect() as db:
                args=[book,cursor];where='book_id=? AND no>? AND deleted_batch IS NULL AND segments>0'
                if chapter_no is not None:where+=' AND no=?';args.append(chapter_no)
                rows=db.execute('SELECT no,title,segments,revision,review FROM lf_chapters WHERE '+where+' ORDER BY no LIMIT 100',args).fetchall()
            if not rows:return
            for row in rows:cursor=row[0];yield dict(zip(['no','title','segments','revision','review'],row))
    def segment_rows(self,book,chapter):
        cursor=0
        while True:
            with self.store.connect() as db:rows=db.execute("SELECT no,start_byte,end_byte,text_sha256,take,status FROM lf_segments WHERE book_id=? AND chapter_no=? AND deleted_batch IS NULL AND no>? ORDER BY no LIMIT 100",(book,chapter,cursor)).fetchall()
            if not rows:return
            for row in rows:
                cursor=row[0];item=dict(zip(['no','start_byte','end_byte','text_sha256','take','status'],row));item['take']=json.loads(item['take']) if item['take'] else None;yield item
    def convert(self,source,target,format,identity):
        log=target.with_suffix('.ffmpeg.log')
        with log.open('wb') as output:
            process=subprocess.Popen([self.owner.platform.config['ffmpeg'],'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source),str(target)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=output)
            lease=None
            try:
                lease=ProcessOwner(process.pid)
                while process.poll() is None:self.check(identity);self.owner.stop_event.wait(.2)
                if process.returncode:raise ValueError('编码失败，原始合成 WAV 保留；查看 '+str(log))
            finally:
                kill_worker(process)
                if lease:lease.close()
    def run(self,item):
        identity=item['id'];book=self.db.book(item['book_id']);request=item['request'];folder=self.owner.root/book['id']/'exports'/identity;folder.mkdir(parents=True,exist_ok=True)
        prefix='DRAFT_' if request['draft'] else '';mode=request['mode'];format=request['format'];pause=book['config']['pause_ms'];rate=None;book_frames=0;files=[];chapter_done=0;cue=0
        summary=dict(id=identity,book_id=book['id'],title=book['title'],draft=request['draft'],request=request,source_sha256=book['source_sha256'],normalized_sha256=book['normalized_sha256'],config_sha256=book['config_sha256'],snapshot=book['snapshot'],timestamp_kind='segment_boundaries_not_forced_alignment',created_at=now(),assembly_pause_ms=pause)
        (folder/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        files.append(folder/'manifest.json')
        metadata=folder/'segments.jsonl';chapter_metadata=folder/'chapters.jsonl';subtitles=folder/'book.srt'
        with metadata.open('w',encoding='utf-8') as ledger,chapter_metadata.open('w',encoding='utf-8') as chapter_ledger,subtitles.open('w',encoding='utf-8') as srt:
            for chapter in self.chapter_rows(book['id'],request['chapter_no']):
                self.check(identity)
                # Freeze of generation is enforced while this export is queued/running.
                if chapter['review']!='approved' and not request['draft']:raise ValueError('章节审核状态变化，请重新提交')
                with self.store.connect() as db:
                    row=db.execute("SELECT take FROM lf_segments WHERE book_id=? AND chapter_no=? AND deleted_batch IS NULL AND status='succeeded' ORDER BY no LIMIT 1",(book['id'],chapter['no'])).fetchone()
                    totals=db.execute("SELECT SUM(json_extract(take,'$.frames')),COUNT(*) FROM lf_segments WHERE book_id=? AND chapter_no=? AND deleted_batch IS NULL AND status='succeeded'",(book['id'],chapter['no'])).fetchone()
                if not row or totals[1]!=chapter['segments']:raise ValueError('章节生成不完整')
                first=json.loads(row[0]);rate=rate or first['sample_rate'];gap=round(rate*pause/1000);frames=int(totals[0])+gap*max(0,totals[1]-1)
                name=f'{prefix}{chapter["no"]:06d}_{safe_name(chapter["title"])}';wave=folder/(name+'.wav');written=0;index=0;chapter_srt=wave.with_suffix('.srt')
                with chapter_srt.open('w',encoding='utf-8') as local_srt,sf.SoundFile(wave,'w',samplerate=rate,channels=1,format=wav_container(frames),subtype='PCM_24') as out:
                    for segment in self.segment_rows(book['id'],chapter['no']):
                        self.check(identity);take=segment['take']
                        if segment['status']!='succeeded' or not take or take['sample_rate']!=rate:raise ValueError('分段状态或采样率不一致')
                        path=self.owner.audio(book['id'],segment['no'])
                        if index:out.write(np.zeros(gap,dtype=np.float32));written+=gap
                        start=written/rate;text=self.owner.text(book,segment)
                        with sf.SoundFile(path) as source:
                            while len(block:=source.read(book['config']['block_frames'],dtype='float32')):self.check(identity);out.write(block);written+=len(block)
                        end=written/rate;cue+=1
                        srt.write(f'{cue}\n{srt_time(book_frames/rate+start)} --> {srt_time(book_frames/rate+end)}\n{text}\n\n')
                        local_srt.write(f'{index+1}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n\n')
                        ledger.write(json.dumps(dict(book_id=book['id'],chapter_no=chapter['no'],segment_no=segment['no'],text=text,start=start,end=end,book_start=book_frames/rate+start,book_end=book_frames/rate+end,source_start_byte=segment['start_byte'],source_end_byte=segment['end_byte'],take=take),ensure_ascii=False)+'\n');index+=1
                if written!=frames:raise ValueError('导出采样帧数校验失败')
                chapter_done+=1;book_frames+=written
                chapter_ledger.write(json.dumps(dict(**chapter,frames=written,sample_rate=rate,file=wave.name,sha256=sha256(wave),duration=written/rate),ensure_ascii=False)+'\n')
                if mode=='chapters':
                    target=wave if format=='wav' else wave.with_suffix('.'+format)
                    if format!='wav':self.convert(wave,target,format,identity)
                    files.extend([target,chapter_srt])
                item.update(progress=round(90*chapter_done/(1 if request['chapter_no'] is not None else book['chapters']),1),message=f'已合成 {chapter_done} 章')
                with self.store.lock:self.check(identity);self.db.save_export(item)
        if mode=='book':
            wave=folder/(prefix+safe_name(book['title'])+'.wav')
            with sf.SoundFile(wave,'w',samplerate=rate,channels=1,format=wav_container(book_frames),subtype='PCM_24') as output:
                with chapter_metadata.open(encoding='utf-8') as chapters:
                    for line in chapters:
                        with sf.SoundFile(folder/json.loads(line)['file']) as source:
                            while len(block:=source.read(book['config']['block_frames'],dtype='float32')):self.check(identity);output.write(block)
            target=wave if format=='wav' else wave.with_suffix('.'+format)
            if format!='wav':self.convert(wave,target,format,identity)
            files.append(target)
        self.check(identity);files.extend([metadata,chapter_metadata,subtitles])
        package=folder/(prefix+'book-export.zip')
        with zipfile.ZipFile(package,'w',allowZip64=True) as archive:
            for file in files:
                self.check(identity)
                with file.open('rb') as source,archive.open(file.name,'w',force_zip64=True) as output:
                    while block:=source.read(1024*1024):self.check(identity);output.write(block)
        item.update(state='succeeded',progress=100,message='导出完成，原分段及合成 WAV 保留',path=str(package.relative_to(self.owner.data)),sha256=sha256(package),bytes=package.stat().st_size,chapters=chapter_done,duration=book_frames/rate,sample_rate=rate,finished_at=now())
        with self.store.lock:self.check(identity);self.db.save_export(item)
