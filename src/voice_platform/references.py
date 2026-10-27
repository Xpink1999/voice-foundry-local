"""Durable recording/clip library, preprocessing queue and controlled clone comparison."""
import copy
import logging
import threading
from pathlib import Path
from .audio import sha256,safe_name
from .schemas import GenerationInput,VoiceInput
from .store import uid,now

log=logging.getLogger(__name__)

class ReferenceLibrary:
    def __init__(self,platform):
        self.platform=platform;self.store=platform.store;self.config=platform.config;self.data=platform.data
        self.options=self.config.get('reference_preprocessing',{})
        self.stop_event=threading.Event();self.wake=threading.Event();self.thread=None;self.process=None

    def start(self):
        if not self.options.get('enabled',False):return
        for kind in ('recordings','reference_comparisons'):
            for item in self.store.list(kind):
                if item['status'] in {'running','cancel_requested'}:
                    changes=dict(status='cancelled' if item['status']=='cancel_requested' else 'failed',error='预处理服务中断；原始录音及已有片段保留，可重试')
                    if item['status']=='cancel_requested' and item.get('smart_reference'):changes['smart_reference']=dict(item['smart_reference'],status='cancelled')
                    self.store.update(kind,item['id'],**changes)
        self.stop_event.clear();self.thread=threading.Thread(target=self._work,name='reference-worker',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        if self.thread:self.thread.join(timeout=10)

    def upload(self,filename,content,source,authorization,rights,smart_reference=False,metadata=None):
        if self.platform.shutdown.is_set():raise ValueError('服务正在停止，请重新启动后提交')
        if not self.options.get('enabled'):raise ValueError('参考预处理未启用，请检查配置')
        if sum(r['status'] in {'queued','running','cancel_requested'} for r in self.store.list('recordings'))>=self.options.get('max_pending_recordings',10):raise ValueError('录音预处理队列已满，请稍后重试')
        if not source.strip() or not authorization.strip():raise ValueError('请填写来源与授权说明')
        if len(content)>self.config['max_upload_mb']*1024**2:raise ValueError('上传超过大小限制')
        suffix=Path(filename).suffix.lower()
        if suffix not in {'.wav','.mp3','.flac','.ogg','.m4a','.aac','.wma','.opus','.webm'}:raise ValueError('请选择受支持的音频格式')
        identity=uid();folder=self.data/'recordings'/identity;folder.mkdir(parents=True)
        original=folder/('original'+suffix);original.write_bytes(content)
        item=dict(id=identity,original_name=safe_name(filename),original_path=str(original.relative_to(self.data)),original_sha256=sha256(original),
                  source=source.strip(),authorization=authorization.strip(),rights_confirmed=rights,status='queued',progress=0,
                  message='等待自动预处理',candidate_ids=[],attempt=0,error=None,created_at=now())
        if metadata:item.update(metadata)
        if smart_reference:item['smart_reference']=dict(status='analyzing',message='正在识别人声与录音质量，随后自动分离并提出参考推荐')
        self.store.save('recordings',item);self.wake.set();return item

    def _decode(self,recording,folder):
        source=self.data/recording['original_path']
        if sha256(source)!=recording['original_sha256']:raise ValueError('原始录音哈希不匹配')
        target=folder/'analysis.wav'
        command=[self.config['ffmpeg'],'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-i',str(source),'-t',str(self.options['max_recording_seconds']+1),
                 '-vn','-ac','1','-ar',str(self.options['sample_rate']),'-c:a','pcm_s16le',str(target)]
        from .worker_runner import run_command
        result=run_command(command,self.stop_event)
        if result.returncode:raise ValueError('音频解码失败：'+result.stderr.decode('utf-8',errors='replace')[-1200:])
        import soundfile as sf
        info=sf.info(target)
        if not .5<=info.duration<=self.options['max_recording_seconds']:raise ValueError(f"录音需为 0.5–{self.options['max_recording_seconds']} 秒，推荐参考片段为 5–30 秒")
        self.store.update('recordings',recording['id'],duration=info.duration,analysis_path=str(target.relative_to(self.data)))
        return dict(recording,analysis_path=str(target),duration=info.duration)

    def _run_worker(self,request,folder,kind,identity):
        from .worker_runner import run_worker
        return run_worker(self,request,folder,kind,identity)

    def _analyze(self,recording):
        attempt=recording.get('attempt',0)+1
        folder=self.data/'recordings'/recording['id']/f'analysis-{attempt}-{uid()[:8]}'
        with self.store.lock:
            current=self.store.get('recordings',recording['id'])
            if self.stop_event.is_set() or current['status']!='queued' or current.get('deleted_at'):raise InterruptedError('排队分析已停止，原件保留')
            folder.mkdir(parents=True)
            self.store.update('recordings',recording['id'],status='running',attempt=attempt,progress=1,error=None,message='解码并保留原始录音')
        decoded=self._decode(recording,folder)
        if self.stop_event.is_set() or self.store.get('recordings',recording['id'])['status']=='cancel_requested':raise InterruptedError('录音分析已停止，原件保留')
        result=self._run_worker(dict(mode='analyze',recording=decoded),folder,'recordings',recording['id'])
        candidates=[]
        for index,clip in enumerate(result['clips']):
            identity=uid();path=Path(clip.pop('file'));embedding=clip.pop('embedding')
            reference=dict(clip,id=identity,recording_id=recording['id'],original_name=f"{recording['original_name']} · 片段 {index+1}",
                path=str(path.relative_to(self.data)),original_path=recording['original_path'],original_sha256=recording['original_sha256'],
                source=recording['source'],authorization=recording['authorization'],rights_confirmed=recording['rights_confirmed'],
                saved=False,embedding=embedding,analysis_models=result['summary']['models'],transcript_history=[],created_at=now())
            for key in ('root_recording_id','processing_id','processing_output_id','source_lineage','source_label'):
                if key in recording:reference[key]=recording[key]
            candidates.append(reference)
        with self.store.lock:
            old=self.store.get('recordings',recording['id'])
            if self.stop_event.is_set() or old['status']=='cancel_requested':raise InterruptedError('录音分析已停止，原件和已有片段保留')
            for reference in candidates:self.store.save('references',reference)
            self.store.update('recordings',recording['id'],status='succeeded',progress=100,message='候选片段已生成，请试听选择并保存',
                              summary=result['summary'],candidate_ids=old['candidate_ids']+[r['id'] for r in candidates],finished_at=now())

    def _work(self):
        while not self.stop_event.is_set():
            recordings=self.store.by_status('recordings',['queued'],limit=1)
            comparisons=[c for c in self.store.list('reference_comparisons') if c['status']=='generating' and self._comparison_ready(c)]
            item=recordings[0] if recordings else comparisons[-1] if comparisons else None
            if not item:self.wake.wait(.7);self.wake.clear();continue
            kind='recordings' if recordings else 'reference_comparisons'
            try:
                if kind=='recordings':self._analyze(item)
                else:self._score_comparison(item)
            except Exception as error:
                log.exception('reference processing failed: %s',item['id'])
                self.store.update(kind,item['id'],status='cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error),message='原始录音与已有资产已保留')

    def detail(self,identity):
        item=self.store.get('recordings',identity)
        candidates=self.platform.restoration.candidates(item)
        ranked=item.get('smart_reference',{}).get('recommendations') or self.platform.restoration.recommendations(candidates)
        children=[{k:r.get(k) for k in ('id','source_label','status','error')} for r in self.store.list('recordings') if r.get('root_recording_id')==identity]
        return dict(item,candidates=candidates,recommendations=ranked,analysis_children=children)

    def save(self,identity,reference_ids):
        recording=self.store.get('recordings',identity)
        if recording.get('deleted_at'):raise ValueError('录音已在回收站，请先恢复')
        if not set(reference_ids)<={r['id'] for r in self.platform.restoration.candidates(recording)}:raise ValueError('片段不属于此录音或其处理结果')
        with self.store.lock:
            for rid in reference_ids:self.store.update('references',rid,saved=True,saved_at=now())
        return [self.store.get('references',r) for r in reference_ids]

    def transcript(self,identity,request):
        with self.store.lock:
            item=self.store.get('references',identity);old=item.get('transcript',{})
            if item.get('deleted_at'):raise ValueError('参考已在回收站，请先恢复')
            value=dict(old,text=request.text,confirmed=request.confirmed,version=old.get('version',1)+1,status='confirmed' if request.confirmed else 'edited_unconfirmed',edited_at=now(),source='user_edit')
            return self.store.update('references',identity,transcript=value,transcript_history=item.get('transcript_history',[])+[dict(old,replaced_at=now())])

    def annotate(self, identity, request):
        with self.store.lock:
            item = self.store.get('references', identity)
            if item.get('deleted_at'):raise ValueError('参考已在回收站，请先恢复')
            changes = request.model_dump(exclude_unset=True)
            previous = {key:item.get(key, [] if key=='tags' else '') for key in changes}
            if changes == previous:return item
            return self.store.update('references', identity, **changes, updated_at=now(),
                metadata_history=item.get('metadata_history', [])+[dict(previous, replaced_at=now())])

    def attach(self, voice_id, request):
        # One version for the whole selection; preserve a previously confirmed default.
        with self.store.lock:
            voice = self.store.get('voices', voice_id)
            if voice.get('deleted_at') or voice['status']=='archived':raise ValueError('请先恢复人物，再添加参考')
            refs = [self.store.get('references', identity) for identity in dict.fromkeys(request.reference_ids)]
            body = {key:voice[key] for key in VoiceInput.model_fields if key in voice}
            body['reference_ids'] = list(dict.fromkeys([voice.get('reference_id')]+voice.get('reference_ids',[])+[r['id'] for r in refs]))
            body['reference_ids'] = [identity for identity in body['reference_ids'] if identity]
            body['reference_scenarios'] = dict(voice.get('reference_scenarios',{}))
            for ref in refs:
                if ref.get('scenario') and ref['id'] not in body['reference_scenarios']:
                    body['reference_scenarios'][ref['id']] = ref['scenario']
            if not body.get('reference_id'):
                body.update(reference_id=refs[0]['id'], reference_confirmed=False, status='draft')
            return self.platform.create_voice(VoiceInput(**body), voice_id)

    def retry(self,identity):
        item=self.store.get('recordings',identity)
        if self.platform.shutdown.is_set():raise ValueError('服务正在停止，请重新启动后提交')
        if item.get('deleted_at'):raise ValueError('录音已在回收站，请先恢复')
        if item['status'] not in {'failed','cancelled'}:raise ValueError('只可重试失败或已取消的录音分析')
        changes=dict(status='queued',progress=0,error=None)
        if item.get('smart_reference'):changes['smart_reference']=dict(status='analyzing',message='正在重新分析原录音')
        self.store.update('recordings',identity,**changes)
        if item.get('root_recording_id'):
            root=self.store.get('recordings',item['root_recording_id']);workflow=root.get('smart_reference')
            if workflow and workflow['status']=='partial' and workflow.get('processing_id')==item.get('processing_id'):
                self.store.update('recordings',root['id'],smart_reference=dict(workflow,status='analyzing_outputs',message='正在重试失败的参考分析，已有处理结果保留'))
                self.platform.restoration.wake.set()
        self.wake.set();return self.store.get('recordings',identity)

    def cancel(self,identity):
        with self.store.lock:
            item=self.store.get('recordings',identity)
            if item['status'] in {'queued','running'}:item=self.store.update('recordings',identity,status='cancelled' if item['status']=='queued' else 'cancel_requested')
        workflow=item.get('smart_reference')
        if workflow and workflow['status'] not in {'ready','partial','failed','cancelled'}:
            if workflow.get('processing_id'):
                task=self.platform.restoration.cancel(workflow['processing_id'])
                for child in task['child_recording_ids']:self.cancel(child)
            item=self.store.update('recordings',identity,smart_reference=dict(workflow,status='cancelled',message='智能整理已停止，原件和已有候选保留'))
        return item

    def compare(self,request):
        voice=self.store.get('voices',request.voice_id);refs=[self.store.get('references',r) for r in dict.fromkeys(request.reference_ids)]
        if len(refs)<2 or len(set(request.seeds))<2:raise ValueError('请选择至少两个不同片段和两个不同种子')
        if any(not r.get('embedding') for r in refs):raise ValueError('所选片段需先完成自动分析，旧参考可重新上传预处理')
        jobs=[];mapping={}
        for reference in refs:
            mapping[reference['id']]=[]
            for seed in request.seeds:
                job=GenerationInput(text=request.text,title=f"参考对比 · {voice['name']} · {reference['id'][:6]} · {seed}",
                    voice_id=voice['id'],project_id=voice['project_id'],reference_id=reference['id'],clone_mode=request.clone_mode,seed=seed,max_retries=0)
                jobs.append(job)
        submitted=self.platform.submit(jobs,batch=True)
        for reference,offset in zip(refs,range(0,len(submitted),len(request.seeds))):mapping[reference['id']]=[j['id'] for j in submitted[offset:offset+len(request.seeds)]]
        identity=uid();item=dict(id=identity,voice_id=voice['id'],voice_version=voice['version'],reference_ids=[r['id'] for r in refs],reference_snapshots=copy.deepcopy(refs),
            job_mapping=mapping,text=request.text,seeds=request.seeds,clone_mode=request.clone_mode,status='generating',progress=0,created_at=now(),error=None)
        self.store.save('reference_comparisons',item);self.wake.set();return item

    def _comparison_ready(self,item):
        return all(self.store.get('jobs',j)['status'] in {'succeeded','failed','cancelled'} for group in item['job_mapping'].values() for j in group)

    def _score_comparison(self,item):
        entries=[];failures=[]
        for reference in item['reference_snapshots']:
            jobs=[self.store.get('jobs',j) for j in item['job_mapping'][reference['id']]]
            if any(j['status']!='succeeded' for j in jobs):failures.append(reference['id']);continue
            results=[self.store.get('results',j['results'][0]) for j in jobs]
            entries.append(dict(reference_id=reference['id'],embedding=reference['embedding'],quality_score=reference.get('quality',{}).get('score',.5),
                audio_paths=[str(self.data/r['path']) for r in results],result_ids=[r['id'] for r in results]))
        if len(entries)<2:raise ValueError('至少两个片段的全部候选生成成功后才可比较；已有结果已保留')
        folder=self.data/'reference-comparisons'/item['id'];self.store.update('reference_comparisons',item['id'],status='running',message='正在评分')
        result=self._run_worker(dict(mode='compare',items=entries,text=item['text']),folder,'reference_comparisons',item['id'])
        self.store.update('reference_comparisons',item['id'],status='succeeded',progress=100,finished_at=now(),failed_references=failures,**result)

    def apply_recommendation(self,identity):
        item=self.store.get('reference_comparisons',identity)
        if item['status']!='succeeded' or not item.get('recommended_reference_id'):raise ValueError('比较尚未完成')
        voice=self.store.get('voices',item['voice_id'])
        if voice['version']!=item['voice_version']:raise ValueError('音色在比较期间已修改，请重新比较或手动选择参考，防止覆盖新版本')
        body={k:voice[k] for k in VoiceInput.model_fields if k in voice}
        body.update(reference_id=item['recommended_reference_id'],reference_ids=list(dict.fromkeys(voice.get('reference_ids',[])+item['reference_ids'])),reference_confirmed=False,status='draft')
        updated=self.platform.create_voice(VoiceInput(**body),voice['id'])
        self.store.update('reference_comparisons',identity,applied_voice_version=updated['version'])
        return updated
