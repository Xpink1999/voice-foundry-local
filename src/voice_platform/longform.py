"""Streaming book import and independently checkpointed segment production."""
import codecs
import hashlib
import io
import json
import logging
import re
import threading
import time
from pathlib import Path
import numpy as np
from .audio import sha256,write_wav
from .schemas import GenerationInput,LongformRegenerationInput
from .store import now,uid
from .longform_store import LongformStore

log=logging.getLogger(__name__)
DEFAULTS=dict(max_source_bytes=2147483648,segment_chars=160,fallback_chapter_chars=30000,import_batch_segments=1000,pause_ms=180,block_frames=65536)
ENCODINGS={'auto','utf-8-sig','utf-16','utf-16-le','utf-16-be','gb18030','gbk','gb2312'}
HEADING=re.compile(r'^(?:第[零〇一二三四五六七八九十百千万两0-9０-９]+[章节回卷部集篇](?:\s|[：:、.．]|$).{0,100}|第[零〇一二三四五六七八九十百千万两0-9０-９]+[章节回卷部集篇].{0,60}|chapter\s+[0-9ivxlcdm]+\b.{0,100}|序章|序言|前言|楔子|引子|尾声|终章|后记|附录)$',re.I)

class Paused(Exception):pass

def detect_encoding(path,requested='auto'):
    if requested not in ENCODINGS:raise ValueError('不支持的文本编码')
    if requested!='auto':return requested
    with Path(path).open('rb') as f:head=f.read(4)
    if head.startswith(codecs.BOM_UTF8):return 'utf-8-sig'
    if head.startswith((codecs.BOM_UTF16_LE,codecs.BOM_UTF16_BE)):return 'utf-16'
    decoder=codecs.getincrementaldecoder('utf-8')('strict')
    try:
        with Path(path).open('rb') as f:
            while chunk:=f.read(1024*1024):
                text=decoder.decode(chunk)
                if '\x00' in text:raise ValueError('文本含空字符；无 BOM 的 UTF-16 请手动选择字节序')
            decoder.decode(b'',final=True)
        return 'utf-8-sig'
    except UnicodeDecodeError:return 'gb18030'

def text_units(stream):
    """Bound even an unbroken multi-million-character line; normal headings remain entire lines."""
    pending=''
    while chunk:=stream.read(65536):
        pending+=chunk
        while pending:
            index=pending.find('\n')
            if 0<=index<8192:
                yield pending[:index+1],True;pending=pending[index+1:]
            elif len(pending)>=8192:
                yield pending[:8192],False;pending=pending[8192:]
            else:break
    if pending:yield pending,True

class Longform:
    def __init__(self,platform):
        self.platform=platform;self.store=platform.store;self.db=LongformStore(self.store)
        self.options={**DEFAULTS,**platform.config.get('longform',{})}
        self.data=platform.data;self.root=self.data/'longform';self.root.mkdir(exist_ok=True)
        self.stop_event=threading.Event();self.wake=threading.Event();self.threads=[]
        from .longform_export import LongformExport
        self.exporter=LongformExport(self)
    def start(self):
        with self.store.connect() as db:
            db.execute("UPDATE lf_books SET phase='failed',error='导入被中断，原文件保留，可重新解析' WHERE phase IN ('uploading','indexing')")
            db.execute("UPDATE lf_books SET state='paused',error='服务重启，已完成段保留；点击续作继续' WHERE state='running'")
            db.execute("UPDATE lf_segments SET status='pending',error='生成中断，可续作' WHERE status='running'")
            db.execute("UPDATE lf_exports SET state='interrupted' WHERE state IN ('running','cancel_requested')")
        self.stop_event.clear()
        for target,name in [(self._import_loop,'book-import'),(self._generate_loop,'book-production'),(self.exporter.loop,'book-export')]:
            t=threading.Thread(target=target,name=name,daemon=True);self.threads.append(t);t.start()
    def stop(self):
        self.stop_event.set();self.wake.set()
        for t in self.threads:t.join(timeout=10)
    def book(self,identity):
        item=self.db.book(identity)
        if item.get('deleted_batch'):raise ValueError('作品已移入回收站，请先恢复')
        return self.db.public(item)
    def _body(self,identity,**values):
        with self.store.lock,self.store.connect() as db:
            row=db.execute('SELECT body FROM lf_books WHERE id=?',(identity,)).fetchone()
            if not row:raise KeyError('长文作品不存在')
            body=json.loads(row[0]);body.update(values);db.execute('UPDATE lf_books SET body=? WHERE id=?',(json.dumps(body,ensure_ascii=False),identity))
    async def upload(self,file,title,encoding,request):
        if encoding not in ENCODINGS:raise ValueError('不支持的文本编码')
        if Path(file.filename or '').suffix.lower() not in {'.txt','.md'}:raise ValueError('整本导入目前支持 TXT / Markdown 文本')
        frozen=self.platform.prepare_job(request)
        with self.store.lock,self.store.connect() as db:
            if db.execute("SELECT COUNT(*) FROM lf_books WHERE phase IN ('uploading','queued','indexing')").fetchone()[0]>=3:raise ValueError('已有三份文本等待导入，请稍后再试')
            identity=uid();folder=self.root/identity;folder.mkdir();path=folder/'source.original'
            body=dict(id=identity,title=title or Path(file.filename).stem[:100],original_name=file.filename,original_path=str(path.relative_to(self.data)),encoding_requested=encoding,upload_complete=False,
                snapshot=frozen,config=dict(self.options),created_at=now(),voice_name=(frozen['voice_snapshot'] or {}).get('name','自动声音（建议使用固定参考）'))
            db.execute('INSERT INTO lf_books(id,body,phase,state,created_at) VALUES (?,?,?,?,?)',(identity,json.dumps(body,ensure_ascii=False),'uploading','paused',body['created_at']))
        size=0;digest=hashlib.sha256()
        try:
            with path.open('xb') as out:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>self.options['max_source_bytes']:raise ValueError('文件超过长文导入配置的字节限制；原始已接收部分保留')
                    await __import__('asyncio').to_thread(out.write,chunk);digest.update(chunk)
            if not size:raise ValueError('文本文件为空')
            self._body(identity,source_sha256=digest.hexdigest(),source_bytes=size,upload_complete=True)
            self.db.update(identity,phase='queued');self.wake.set();return self.book(identity)
        except BaseException as error:
            self.db.update(identity,phase='failed',error=str(error)[:1000]);raise
    def retry_import(self,identity,encoding):
        with self.store.lock:
            book=self.db.book(identity)
            if book['phase']!='failed' or not book['upload_complete']:raise ValueError('仅能重新解析上传完整且解析失败的原件')
            if encoding not in ENCODINGS:raise ValueError('不支持的文本编码')
            self._body(identity,encoding_requested=encoding);self.db.update(identity,phase='queued',error=None);self.wake.set();return self.book(identity)
    def _import_loop(self):
        while not self.stop_event.is_set():
            with self.store.connect() as db:row=db.execute("SELECT id FROM lf_books WHERE phase='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:self.wake.wait(.5);self.wake.clear();continue
            try:self.import_book(row[0])
            except Exception as error:
                log.exception('book import %s',row[0]);self.db.update(row[0],phase='failed',error=('编码或文本解析失败：'+str(error))[:2000])
    def import_book(self,identity):
        book=self.db.book(identity);path=self.data/book['original_path'];self.db.update(identity,phase='indexing',error=None)
        if sha256(path)!=book['source_sha256']:raise ValueError('原始文件哈希变化，拒绝解析')
        encoding=detect_encoding(path,book['encoding_requested']);folder=self.root/identity;target=folder/('text-'+uid()+'.utf8');config=book['config'];limit=config['segment_chars']
        if not 40<=limit<=500:raise ValueError('长文段长须在 40–500 字符之间')
        chapter=0;position=0;number=0;chars=0;chapter_chars=0;fallback=False;batch=[];stats={};buffer='';buffer_offset=0
        def flush(db):
            if batch:
                db.executemany('INSERT INTO lf_segments(book_id,no,chapter_no,chapter_pos,start_byte,end_byte,chars,text_sha256) VALUES (?,?,?,?,?,?,?,?)',batch)
                for ch,(n,c) in stats.items():db.execute('UPDATE lf_chapters SET segments=segments+?,chars=chars+? WHERE book_id=? AND no=?',(n,c,identity,ch))
                batch.clear();stats.clear()
            db.execute('UPDATE lf_books SET chars=?,chapters=?,segments=? WHERE id=?',(chars,chapter,number,identity));db.commit()
        with self.store.connect() as db,path.open('r',encoding=encoding,errors='strict',newline=None) as stream,target.open('xb') as normalized:
            db.execute('DELETE FROM lf_segments WHERE book_id=?',(identity,));db.execute('DELETE FROM lf_chapters WHERE book_id=?',(identity,));db.commit()
            def emit(piece,offset):
                nonlocal number,position,chapter_chars
                spoken=piece.strip()
                if not spoken:return
                leading=piece[:len(piece)-len(piece.lstrip())];start=offset+len(leading.encode('utf-8'));end=start+len(spoken.encode('utf-8'));number+=1;position+=1;chapter_chars+=len(spoken)
                batch.append((identity,number,chapter,position,start,end,len(spoken),hashlib.sha256(spoken.encode('utf-8')).hexdigest()))
                count,total=stats.get(chapter,(0,0));stats[chapter]=(count+1,total+len(spoken))
            def drain(final=False):
                nonlocal buffer,buffer_offset
                while len(buffer)>=limit or (final and buffer):
                    n=min(limit,len(buffer))
                    if not final or len(buffer)>limit:
                        punctuation=max(buffer.rfind(c,0,n) for c in ('。','！','？','.','!','?','；',';','\n'))
                        if punctuation<limit//3:punctuation=max(buffer.rfind(c,0,n) for c in ('，',',','、',' '))
                        if punctuation>=limit//3:n=punctuation+1
                    piece=buffer[:n];emit(piece,buffer_offset);buffer_offset+=len(piece.encode('utf-8'));buffer=buffer[n:]
                    if len(batch)>=config['import_batch_segments']:flush(db)
            for line,complete in text_units(stream):
                if not chapter and not line.strip():normalized.write(line.encode('utf-8'));chars+=len(line);continue
                if self.stop_event.is_set():raise Paused('导入中断，原件保留')
                if '\x00' in line:raise ValueError('文本包含空字符，请检查编码或使用纯文本')
                heading=line.strip().lstrip('#').strip();is_heading=complete and 0<len(heading)<=120 and bool(HEADING.fullmatch(heading) or re.match(r'^#{1,3}\s+\S',line.strip()))
                if not chapter or is_heading or (fallback and chapter_chars>=config['fallback_chapter_chars']):
                    drain(True);chapter+=1;position=0;chapter_chars=0;fallback=not is_heading
                    db.execute('INSERT INTO lf_chapters(book_id,no,title) VALUES (?,?,?)',(identity,chapter,heading if is_heading else ('正文' if chapter==1 else f'正文 · 分章 {chapter}')))
                offset=normalized.tell();encoded=line.encode('utf-8');normalized.write(encoded);chars+=len(line)
                if not buffer:buffer_offset=offset
                buffer+=line;drain(complete)
            drain(True);flush(db)
            # Empty leading/trailing whitespace chapters are not playable and should not become review blockers.
            db.execute('DELETE FROM lf_chapters WHERE book_id=? AND segments=0',(identity,))
            actual=db.execute('SELECT COUNT(*) FROM lf_chapters WHERE book_id=?',(identity,)).fetchone()[0]
            if not number:raise ValueError('未找到可配音的文字')
        metadata=dict(encoding=encoding,normalized_path=str(target.relative_to(self.data)),normalized_sha256=sha256(target),config_sha256=hashlib.sha256(json.dumps(book['snapshot'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),imported_at=now())
        self._body(identity,**metadata);self.db.update(identity,phase='ready',state='paused',chapters=actual,segments=number,chars=chars,done=0,failed=0,error=None)
        (folder/'configuration.json').write_text(json.dumps({**metadata,'snapshot':book['snapshot'],'config':config,'source_sha256':book['source_sha256']},ensure_ascii=False,indent=2),encoding='utf-8')
    def segments(self,identity,chapter,limit=50,offset=0,status=None):
        self.db.chapter(identity,chapter);where='book_id=? AND chapter_no=?';args=[identity,chapter]
        if status:where+=' AND status=?';args.append(status)
        result=self.db.rows('lf_segments',where,args,limit=limit,offset=offset);book=self.db.book(identity)
        for item in result['items']:item['text']=self.text(book,item)
        return result
    def text(self,book,segment):
        with (self.data/book['normalized_path']).open('rb') as f:f.seek(segment['start_byte']);value=f.read(segment['end_byte']-segment['start_byte'])
        if hashlib.sha256(value).hexdigest()!=segment['text_sha256']:raise ValueError('分段文本校验失败，停止生成')
        return value.decode('utf-8')
    def ensure_idle_export(self,identity):
        self.book(identity)
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM lf_exports WHERE book_id=? AND state IN ('queued','running','cancel_requested') LIMIT 1",(identity,)).fetchone():raise ValueError('本作品正在导出，请等待完成或取消导出后再改变生成状态')
    def generation_snapshot(self,book,segment):
        if not segment.get('profile_id'):return book['snapshot']
        with self.store.connect() as db:
            row=db.execute('SELECT body FROM lf_generation_profiles WHERE book_id=? AND id=?',(book['id'],segment['profile_id'])).fetchone()
        if not row:raise ValueError('本段的生成配置缺失，请恢复配置记录')
        if hashlib.sha256(row[0].encode()).hexdigest()!=segment['profile_id']:raise ValueError('本段的生成配置哈希不匹配')
        return json.loads(row[0])
    def generation(self,identity,number):
        book=self.db.book(identity);segment=self.db.segment(identity,number);snapshot=self.generation_snapshot(book,segment)
        reference=snapshot.get('reference_snapshot')
        return dict(book_id=identity,book_state=book['state'],segment_no=number,chapter_no=segment['chapter_no'],status=segment['status'],take=segment.get('take'),text=self.text(book,segment),reference={key:reference.get(key) for key in ('id','name','original_name','source_label','duration','transcript')} if reference else None,
                    style=snapshot['style'],clone_mode=snapshot['request']['clone_mode'],seed=(segment.get('take') or {}).get('seed',snapshot['seed']),
                    engine=snapshot['engine'],voice_id=(snapshot.get('voice_snapshot') or {}).get('id'),book_reference_id=(book['snapshot'].get('reference_snapshot') or {}).get('id'),
                    book_defaults=dict(style=book['snapshot']['style'],clone_mode=book['snapshot']['request']['clone_mode'],seed=book['snapshot']['seed']))
    def regenerate(self,identity,number,request=None):
        request=request or LongformRegenerationInput()
        with self.store.lock,self.store.connect() as db:
            self.ensure_idle_export(identity);book=self.db.book(identity);segment=self.db.segment(identity,number)
            if book['state']=='running' or segment['status']=='running':raise ValueError('请先暂停作品，再重新生成单段')
            if segment['status'] not in {'succeeded','failed'}:raise ValueError('请等待当前段生成完成，再调整参考')
            snapshot=book['snapshot'] if request.use_book_defaults else self.generation_snapshot(book,segment)
            prepared=self.platform.prepare_revision(snapshot,request,text=self.text(book,segment))
            profile={key:prepared[key] for key in ('request','engine','model','voice_snapshot','reference_snapshot','style','seed','runtime','pipeline')}
            if request.seed is not None:profile['segment_seed']=request.seed
            elif not request.use_book_defaults and 'segment_seed' in snapshot:profile['segment_seed']=snapshot['segment_seed']
            body=json.dumps(profile,ensure_ascii=False,sort_keys=True);profile_id=hashlib.sha256(body.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO lf_generation_profiles VALUES (?,?,?)',(identity,profile_id,body))
            done=int(segment['status']=='succeeded');failed=int(segment['status']=='failed')
            db.execute("UPDATE lf_segments SET status='pending',variant=variant+1,profile_id=?,error=NULL WHERE book_id=? AND no=?",(profile_id,identity,number))
            db.execute("UPDATE lf_chapters SET done=done-?,failed=failed-?,revision=revision+1,review='pending' WHERE book_id=? AND no=?",(done,failed,identity,segment['chapter_no']))
            db.execute("UPDATE lf_books SET done=done-?,failed=failed-?,state=?,active_segment=?,active_chapter=?,error=NULL WHERE id=?",(done,failed,'running' if request.start else 'paused',number,segment['chapter_no'],identity))
        self.wake.set()
        return self.book(identity)
    def use_attempt(self,identity,number,attempt):
        with self.store.lock,self.store.connect() as db:
            self.ensure_idle_export(identity);book=self.db.book(identity);segment=self.db.segment(identity,number)
            if book['state']=='running' or segment['status']=='running':raise ValueError('请先暂停作品，再切换分段版本')
            row=db.execute('SELECT body FROM lf_attempts WHERE book_id=? AND segment_no=? AND attempt=?',(identity,number,attempt)).fetchone()
            if not row:raise KeyError('分段版本不存在')
            take=json.loads(row[0])
            if take.get('status')!='succeeded':raise ValueError('只能采用生成成功的版本')
            self.attempt_audio(identity,number,attempt)
            done=int(segment['status']!='succeeded');failed=int(segment['status']=='failed')
            db.execute("UPDATE lf_segments SET status='succeeded',take=?,profile_id=?,error=NULL WHERE book_id=? AND no=?",(json.dumps(take,ensure_ascii=False),take.get('generation_profile_id'),identity,number))
            db.execute("UPDATE lf_chapters SET done=done+?,failed=failed-?,revision=revision+1,review='pending' WHERE book_id=? AND no=?",(done,failed,identity,segment['chapter_no']))
            db.execute("UPDATE lf_books SET done=done+?,failed=failed-?,state='paused',active_segment=NULL,error=NULL WHERE id=?",(done,failed,identity))
            total,expected,failures=db.execute('SELECT done,segments,failed FROM lf_books WHERE id=?',(identity,)).fetchone()
            db.execute('UPDATE lf_books SET state=? WHERE id=?',('completed' if total==expected else 'attention' if failures else 'paused',identity))
        return self.db.segment(identity,number)
    def attempt_audio(self,identity,number,attempt):
        self.book(identity);self.db.segment(identity,number)
        with self.store.connect() as db:row=db.execute('SELECT body FROM lf_attempts WHERE book_id=? AND segment_no=? AND attempt=?',(identity,number,attempt)).fetchone()
        if not row:raise KeyError('分段版本不存在')
        take=json.loads(row[0])
        if take.get('status')!='succeeded':raise ValueError('该版本没有完整音频')
        path=self.data/take['path']
        if not path.is_file() or sha256(path)!=take['sha256']:raise ValueError('版本音频缺失或哈希不匹配')
        return path
    def resume(self,identity,chapter=None):
        with self.store.lock:
            book=self.db.book(identity);self.ensure_idle_export(identity)
            if book['phase']!='ready':raise ValueError('请等待文本解析完成')
            if chapter is not None:self.db.chapter(identity,chapter)
            self.db.update(identity,state='running',active_chapter=chapter,active_segment=None,error=None);self.wake.set();return self.book(identity)
    def pause(self,identity):
        self.db.book(identity);return self.db.update(identity,state='paused')
    def retry(self,identity,number=None,chapter=None):
        with self.store.lock,self.store.connect() as db:
            book=self.db.book(identity);self.ensure_idle_export(identity)
            if book['phase']!='ready':raise ValueError('文本尚未准备好')
            where="book_id=? AND status='failed'";args=[identity]
            if number is not None:where+=' AND no=?';args.append(number);self.db.segment(identity,number)
            if chapter is not None:where+=' AND chapter_no=?';args.append(chapter);self.db.chapter(identity,chapter)
            counts=db.execute('SELECT chapter_no,COUNT(*) FROM lf_segments WHERE '+where+' GROUP BY chapter_no',args).fetchall()
            db.execute("UPDATE lf_segments SET status='pending',error=NULL WHERE "+where,args)
            total=0
            for ch,count in counts:
                total+=count;db.execute("UPDATE lf_chapters SET failed=failed-?,review='pending' WHERE book_id=? AND no=?",(count,identity,ch))
            db.execute('UPDATE lf_books SET failed=failed-? WHERE id=?',(total,identity))
        self.wake.set();return dict(retried=total,book=self.book(identity))
    def review(self,identity,chapter,request):
        with self.store.lock,self.store.connect() as db:
            row=self.db.chapter(identity,chapter)
            if not row['segments']:raise ValueError('本章没有可试听的有效分段')
            if row['done']!=row['segments'] or row['failed']:raise ValueError('本章尚未全部生成成功，不能审核完整章节')
            if request.status=='approved' and not request.listened:raise ValueError('请实际试听本章后确认')
            db.execute('UPDATE lf_chapters SET review=?,review_version=revision,review_note=?,reviewer=?,reviewed_at=? WHERE book_id=? AND no=?',(request.status,request.note,request.reviewer,now(),identity,chapter))
            db.execute('INSERT INTO lf_reviews VALUES (?,?,?,?,?)',(uid(),identity,chapter,row['revision'],json.dumps(dict(**request.model_dump(),created_at=now()),ensure_ascii=False)))
        return self.db.chapter(identity,chapter)
    def next_audio(self,identity,chapter,after=0):
        self.db.chapter(identity,chapter)
        with self.store.connect() as db:row=db.execute("SELECT no FROM lf_segments WHERE book_id=? AND chapter_no=? AND status='succeeded' AND deleted_batch IS NULL AND no>? ORDER BY no LIMIT 1",(identity,chapter,after)).fetchone()
        if not row:return dict(item=None)
        segment=self.db.segment(identity,row[0]);segment['text']=self.text(self.db.book(identity),segment);return dict(item=segment)
    def check(self,identity):
        if self.stop_event.is_set() or self.db.book(identity)['state']!='running':raise Paused()
    def _generate_loop(self):
        while not self.stop_event.is_set():
            with self.store.connect() as db:row=db.execute("SELECT id FROM lf_books WHERE phase='ready' AND state='running' AND deleted_batch IS NULL ORDER BY created_at LIMIT 1").fetchone()
            if not row:self.wake.wait(.3);self.wake.clear();continue
            try:
                if not self.generate_next(row[0]):self.wake.wait(.1)
            except Paused:pass
            except Exception as error:
                log.exception('longform scheduler');self.db.update(row[0],state='attention',error=str(error)[:2000])
            self.stop_event.wait(.03)
    def generate_next(self,identity):
        book=self.db.book(identity);self.check(identity);where="book_id=? AND status='pending' AND deleted_batch IS NULL";args=[identity]
        if book['active_chapter'] is not None:where+=' AND chapter_no=?';args.append(book['active_chapter'])
        if book.get('active_segment') is not None:where+=' AND no=?';args.append(book['active_segment'])
        with self.store.connect() as db:next_row=db.execute('SELECT no FROM lf_segments WHERE '+where+' ORDER BY no LIMIT 1',args).fetchone()
        if not next_row:
            state='completed' if book['done']==book['segments'] else 'attention' if book['failed'] else 'paused'
            self.db.update(identity,state=state,active_segment=None);return False
        item=self.db.segment(identity,next_row[0]);attempt=item['attempt']+1;folder=self.root/identity/'audio'/f'{item["no"]:09d}'/uid();folder.mkdir(parents=True)
        with self.store.lock,self.store.connect() as db:
            self.check(identity)  # Pause and segment claim share the same lock; no late claim after pause.
            db.execute("UPDATE lf_segments SET status='running',attempt=?,updated_at=? WHERE book_id=? AND no=?",(attempt,now(),identity,item['no']))
        try:
            text=self.text(book,item);snapshot=self.generation_snapshot(book,item);engine=self.platform.engines[snapshot['engine']]
            if engine.identity()!=snapshot['model']:raise ValueError('模型版本已变化，请恢复匹配的模型后续作；成功段保持不变')
            reference=snapshot['reference_snapshot'];reference_path=self.data/reference['path'] if reference else None
            if reference and sha256(reference_path)!=reference['sha256']:raise ValueError('冻结的参考音频哈希不匹配')
            while not self.platform.engine_lock.acquire(timeout=.2):self.check(identity)
            try:
                self.check(identity);self.platform.last_use=time.monotonic()
                self.platform.load_engine(snapshot['engine'])
                request=snapshot['request'];seed=snapshot.get('segment_seed',(snapshot['seed']+item['no']-1+item['variant']*1000003)%2147483647)
                generation=dict(text=text,style=snapshot['style'],seed=seed,engine_options=request['engine_options'],clone_mode=request['clone_mode'],prompt_text=reference.get('transcript',{}).get('text') if reference else None,streaming=True if engine.capabilities().get('streaming') else False,reference_path=str(reference_path) if reference else None)
                chunks=[];stream=engine.synthesize(generation)
                try:
                    for chunk in stream:self.check(identity);chunks.append(np.asarray(chunk,dtype=np.float32).reshape(-1))
                finally:
                    if hasattr(stream,'close'):stream.close()
                pcm=np.concatenate(chunks) if chunks else np.array([]);path=folder/'original.wav';write_wav(path,pcm,engine.sample_rate)
                take=dict(id=folder.name,path=str(path.relative_to(self.data)),sha256=sha256(path),sample_rate=engine.sample_rate,frames=len(pcm),duration=len(pcm)/engine.sample_rate,seed=seed,text_sha256=item['text_sha256'],config_sha256=book['config_sha256'],model=snapshot['model'],attempt=attempt,created_at=now(),review='pending')
                take.update(generation_profile_id=item.get('profile_id'),reference_id=reference['id'] if reference else None,
                            reference_name=(reference.get('name') or reference.get('source_label') or reference.get('original_name')) if reference else None,
                            reference_sha256=reference.get('sha256') if reference else None,clone_mode=request['clone_mode'],style=snapshot['style'])
                (folder/'provenance.json').write_text(json.dumps(take,ensure_ascii=False,indent=2),encoding='utf-8')
            finally:self.platform.last_use=time.monotonic();self.platform.engine_lock.release()
            with self.store.lock,self.store.connect() as db:
                db.execute("UPDATE lf_segments SET status='succeeded',take=?,error=NULL,updated_at=? WHERE book_id=? AND no=?",(json.dumps(take,ensure_ascii=False),now(),identity,item['no']))
                db.execute('INSERT INTO lf_attempts VALUES (?,?,?,?)',(identity,item['no'],attempt,json.dumps(dict(status='succeeded',**take),ensure_ascii=False)))
                db.execute("UPDATE lf_chapters SET done=done+1,revision=revision+1,review='pending' WHERE book_id=? AND no=?",(identity,item['chapter_no']))
                db.execute('UPDATE lf_books SET done=done+1 WHERE id=?',(identity,))
                if book.get('active_segment') is not None:
                    total,expected,failures=db.execute('SELECT done,segments,failed FROM lf_books WHERE id=?',(identity,)).fetchone()
                    db.execute('UPDATE lf_books SET state=?,active_segment=NULL WHERE id=?',('completed' if total==expected else 'attention' if failures else 'paused',identity))
            return True
        except Exception as error:
            paused=isinstance(error,Paused)
            with self.store.lock,self.store.connect() as db:
                db.execute('UPDATE lf_segments SET status=?,error=?,updated_at=? WHERE book_id=? AND no=?',('pending' if paused else 'failed',str(error)[:2000],now(),identity,item['no']))
                db.execute('INSERT OR REPLACE INTO lf_attempts VALUES (?,?,?,?)',(identity,item['no'],attempt,json.dumps(dict(status='interrupted' if paused else 'failed',error=str(error)[:2000],folder=str(folder.relative_to(self.data)),generation_profile_id=item.get('profile_id'),created_at=now()),ensure_ascii=False)))
                if not paused:
                    db.execute("UPDATE lf_chapters SET failed=failed+1,review='pending' WHERE book_id=? AND no=?",(identity,item['chapter_no']))
                    db.execute("UPDATE lf_books SET failed=failed+1,state='attention',error=? WHERE id=?",(f'第 {item["no"]} 段失败：'+str(error)[:1000],identity))
            if paused:raise
            return True
    def audio(self,identity,number):
        item=self.db.segment(identity,number)
        if item['status']!='succeeded' or not item['take']:raise ValueError('该段尚无完整生成结果')
        path=self.data/item['take']['path']
        if not path.is_file() or sha256(path)!=item['take']['sha256']:raise ValueError('分段音频缺失或哈希不匹配，原件记录保留')
        return path
