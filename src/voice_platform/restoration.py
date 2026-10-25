"""Non-destructive restoration queue and the one-upload smart reference workflow."""
import copy
import json
import logging
import threading
from pathlib import Path
import soundfile as sf
from .audio import sha256
from .schemas import ProcessingInput,VoiceInput
from .store import uid,now
from .worker_runner import run_worker,run_command

log=logging.getLogger(__name__)
TERMINAL={'succeeded','failed','cancelled'}


class AudioRestoration:
    def __init__(self,platform):
        self.platform=platform;self.config=platform.config;self.data=platform.data;self.store=platform.store
        self.options=self.config.get('audio_processing',{});self.stop_event=threading.Event();self.wake=threading.Event();self.thread=None;self.process=None

    def start(self):
        if not self.options.get('enabled'):return
        for item in self.store.list('audio_processing'):
            if item['status'] in {'running','cancel_requested'}:self.store.update('audio_processing',item['id'],status='failed',error='处理服务中断，原件与已有结果保留，可创建新处理任务')
        self.stop_event.clear();self.thread=threading.Thread(target=self._work,name='audio-restoration',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        if self.thread:self.thread.join(timeout=10)

    def capabilities(self):
        models=[]
        for operation,key,label,limit in [('remove_music','music_dir','去背景音乐','音乐人声与伴奏两轨，不保证完全去除'),('denoise','enhancement_dir','语音降噪','可能损伤细节，请与原录音比较'),('separate','separation_dir','重叠人声分离','最多两路同时说话；匿名轨道不代表身份，长静音后可能换位')]:
            path=Path(self.options.get(key,''));path=path if path.is_absolute() else Path(self.config['root'])/path
            models.append(dict(operation=operation,label=label,available=self.options.get('enabled',False) and (path/'provenance.json').exists(),note=limit))
        return dict(enabled=self.options.get('enabled',False),device=self.options.get('device'),operations=models,originals_preserved=True)

    def submit(self,request,workflow_root=None):
        if self.platform.shutdown.is_set():raise ValueError('服务正在停止，请重新启动后提交')
        if not self.options.get('enabled'):raise ValueError('音频处理未启用')
        with self.store.lock:
            if sum(i['status'] not in TERMINAL for i in self.store.list('audio_processing'))>=self.options['max_pending']:raise ValueError('音频处理队列已满，请稍后再试')
            source=self.store.get('recordings',request.recording_id)
            if source.get('deleted_at'):raise ValueError('录音已在回收站，请先恢复')
            available={c['operation'] for c in self.capabilities()['operations'] if c['available']}
            if set(request.operations)-available:raise ValueError('所选处理模型尚未完整安装')
            if source['status'] not in TERMINAL:raise ValueError('请等待原录音时长与分析完成')
            item=dict(id=uid(),recording_id=source['id'],root_recording_id=source.get('root_recording_id',source['id']),
                source_snapshot=copy.deepcopy(source),operations=request.operations,analyze_outputs=request.analyze_outputs,
                workflow_root=workflow_root,status='queued',progress=0,message='等待处理；原件保留',outputs=[],child_recording_ids=[],import_errors=[],created_at=now(),error=None)
            item['options_snapshot']=copy.deepcopy(self.options)
            item['model_snapshots']={}
            for operation in request.operations:
                key={'remove_music':'music_dir','separate':'separation_dir','denoise':'enhancement_dir'}[operation]
                path=Path(self.options[key]);path=path if path.is_absolute() else Path(self.config['root'])/path
                item['model_snapshots'][key]=json.loads((path/'provenance.json').read_text(encoding='utf-8'))
            self.store.save('audio_processing',item);self.wake.set();return item

    def cancel(self,identity):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item['status'] not in TERMINAL:item=self.store.update('audio_processing',identity,status='cancelled' if item['status']=='queued' else 'cancel_requested')
        return item

    def _run_worker(self,request,folder,kind,identity):return run_worker(self,request,folder,kind,identity)

    def _decode(self,item,folder):
        source=item['source_snapshot'];path=self.data/source['original_path']
        if sha256(path)!=source['original_sha256']:raise ValueError('原录音哈希不匹配，拒绝处理')
        target=folder/'before.wav';maximum=self.config['reference_preprocessing']['max_recording_seconds']
        result=run_command([self.config['ffmpeg'],'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-i',str(path),'-t',str(maximum+1),'-vn','-ac','2','-ar','48000','-c:a','pcm_s24le',str(target)],self.stop_event)
        if result.returncode:raise ValueError('无法解码待处理录音：'+result.stderr.decode('utf-8',errors='replace')[-1000:])
        if not .5<=sf.info(target).duration<=maximum:raise ValueError('待处理音频超出时长限制')
        self.store.update('audio_processing',item['id'],before_path=str(target.relative_to(self.data)),input_sha256=sha256(target))
        return target

    def _process(self,item):
        folder=self.data/'audio-processing'/item['id'];folder.mkdir(parents=True,exist_ok=True)
        with self.store.lock:
            if self.store.get('audio_processing',item['id'])['status']!='queued':raise InterruptedError('排队处理已停止，原件保留')
            self.store.update('audio_processing',item['id'],status='running',progress=1,message='解码录音，等待可用计算设备',started_at=now())
        source=self._decode(item,folder)
        config=copy.deepcopy(self.config);config['audio_processing']=item['options_snapshot']
        for key,expected in item['model_snapshots'].items():
            path=Path(item['options_snapshot'][key]);path=path if path.is_absolute() else Path(self.config['root'])/path
            if json.loads((path/'provenance.json').read_text(encoding='utf-8'))!=expected:raise ValueError('模型版本已变化，请新建处理任务；原件保留')
        use_gpu=item['options_snapshot']['device'].startswith('cuda');acquired=False
        try:
            if use_gpu:
                while not acquired:
                    if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，原件保留')
                    acquired=self.platform.engine_lock.acquire(timeout=.5)
                if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，原件保留')
                self.platform.unload()  # RLock: release the TTS weights before this owned GPU worker loads its models.
            result=self._run_worker(dict(mode='process',input_path=str(source),operations=item['operations'],config_snapshot=config),folder,'audio_processing',item['id'])
            if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，已有文件保留')
        finally:
            if acquired:self.platform.engine_lock.release()
        outputs=[]
        for output in result['outputs']:
            path=Path(output.pop('file')).resolve()
            path.relative_to(folder.resolve())
            output=dict(output,id=uid(),path=str(path.relative_to(self.data)),processing_id=item['id'],recording_id=None)
            outputs.append(output)
        self.store.update('audio_processing',item['id'],status='succeeded',outputs=outputs,progress=100,message='处理完成，可比较原件与各个结果',model_sources=result['model_sources'],device=result['device'],note=result['note'],finished_at=now())
        errors=[]
        if item['analyze_outputs']:
            for output in outputs:
                if not output['final'] or output['role']!='speech':continue
                try:self.import_output(item['id'],output['id'])
                except Exception as error:errors.append(dict(output_id=output['id'],error=str(error)))
        if errors:self.store.update('audio_processing',item['id'],import_errors=errors,message='处理结果已保留；部分结果未能自动分析，可稍后选用')

    def import_output(self,identity,output_id):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item.get('deleted_at'):raise ValueError('处理记录已在回收站，请先恢复')
            output=next((o for o in item['outputs'] if o['id']==output_id),None)
            if not output:raise KeyError('处理输出不存在')
            if output['role']!='speech':raise ValueError('背景音乐轨不能用作人物声音参考')
            if output.get('recording_id'):
                recording=self.store.get('recordings',output['recording_id'])
                if recording.get('deleted_at'):raise ValueError('处理结果录音已在回收站，请先恢复')
                return recording
            path=self.data/output['path']
            if sha256(path)!=output['sha256']:raise ValueError('处理结果哈希不匹配')
            source=item['source_snapshot']
            metadata=dict(parent_recording_id=item['recording_id'],root_recording_id=item['root_recording_id'],processing_id=identity,
                processing_output_id=output_id,source_label=output['label'],source_lineage=dict(original_sha256=source['original_sha256'],operations=item['operations'],model_sources=item.get('model_sources',{})))
            recording=self.platform.references.upload(output['label']+'.wav',path.read_bytes(),source['source'],source['authorization'],source['rights_confirmed'],metadata=metadata)
            output['recording_id']=recording['id']
            self.store.update('audio_processing',identity,outputs=item['outputs'],child_recording_ids=item['child_recording_ids']+[recording['id']])
            return recording

    def _work(self):
        while not self.stop_event.is_set():
            self.advance_workflows()
            queued=[i for i in self.store.list('audio_processing') if i['status']=='queued']
            if not queued:self.wake.wait(.7);self.wake.clear();continue
            item=queued[-1]
            try:self._process(item)
            except Exception as error:
                log.exception('audio restoration failed: %s',item['id'])
                self.store.update('audio_processing',item['id'],status='cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error),message='原始录音与已有结果已保留',finished_at=now())

    def candidates(self,recording):
        children=[r for r in self.store.list('recordings') if r.get('root_recording_id')==recording['id']]
        recordings=[recording]+children
        items=[]
        for source in recordings:
            for identity in source['candidate_ids']:
                ref=self.store.get('references',identity)
                if ref.get('deleted_at'):continue
                items.append(dict(ref,source_label=source.get('source_label','原录音'),source_recording_id=source['id']))
        return items

    def recommendations(self,candidates):
        from .reference_analysis import cluster
        valid=[r for r in candidates if r.get('transcript',{}).get('text') and r['duration']>=2 and r.get('quality',{}).get('speech_score',1)>=.15]
        valid.sort(key=lambda r:r.get('quality',{}).get('score',.5),reverse=True)
        with_embeddings=[r for r in valid if r.get('embedding')]
        labels,_=cluster([r['embedding'] for r in with_embeddings],self.config['reference_preprocessing']['speaker_similarity_threshold'])
        groups={r['id']:f'声线 {label+1}' for r,label in zip(with_embeddings,labels)}
        ranked=[]
        for r in valid:
            quality=r.get('quality',{});score=quality.get('score',.5)+(.08 if 5<=r['duration']<=30 else 0)-(.2 if r['transcript'].get('low_confidence') else 0)-(.12 if len(r.get('speaker_labels',[]))>1 else 0)
            ranked.append(dict(reference_id=r['id'],score=round(score,4),group=groups.get(r['id'],'待确认声线'),source_label=r.get('source_label','原录音'),
                reason='综合参考时长、人声与噪声检测、转写置信度；为模型推荐，需试听确认'))
        ranked.sort(key=lambda r:r['score'],reverse=True)
        diverse=[];seen=set()
        for item in ranked:
            if item['group'] not in seen:diverse.append(item);seen.add(item['group'])
        diverse.extend(r for r in ranked if r not in diverse)
        return diverse

    def advance_workflows(self):
        for recording in self.store.list('recordings'):
            workflow=recording.get('smart_reference')
            if not workflow or workflow['status'] in {'ready','partial','failed','cancelled'}:continue
            try:
                if recording['status'] in {'failed','cancelled'}:
                    self._workflow(recording,dict(workflow,status='failed',message='原录音仍保留，请重试分析或进入高级处理'));continue
                if recording['status']!='succeeded':continue
                if not workflow.get('processing_id'):
                    # Always produce restoration alternatives, then compare with untouched candidates.
                    # A negative classifier result must not prevent background-removal attempts.
                    operations=['remove_music','separate','denoise']
                    task=self.submit(ProcessingInput(recording_id=recording['id'],operations=operations),workflow_root=recording['id'])
                    self._workflow(recording,dict(workflow,status='processing',processing_id=task['id'],message='正在自动分离与整理，原件候选同时保留'));continue
                task=self.store.get('audio_processing',workflow['processing_id'])
                if task['status'] not in TERMINAL:continue
                children=[self.store.get('recordings',i) for i in task['child_recording_ids']]
                if any(c['status'] not in TERMINAL for c in children):
                    self._workflow(recording,dict(workflow,status='analyzing_outputs',message='处理完成，正在转写、选段并比较候选质量'));continue
                ranked=self.recommendations(self.candidates(recording))
                partial=task['status']!='succeeded' or task.get('import_errors') or any(c['status']!='succeeded' for c in children)
                message='推荐已准备，请试听后保存人物参考' if not partial else '部分处理未完成，已有候选仍可试听与保存；可到高级处理查看原因'
                self._workflow(recording,dict(workflow,status='partial' if partial else 'ready',message=message,recommendations=ranked,finished_at=now()))
            except Exception as error:
                log.exception('smart reference workflow failed: %s',recording['id'])
                self._workflow(recording,dict(workflow,status='partial',message='自动整理未全部完成，原件和可用候选保留',error=str(error),recommendations=self.recommendations(self.candidates(recording))))

    def _workflow(self,recording,workflow):
        if workflow!=recording.get('smart_reference'):self.store.update('recordings',recording['id'],smart_reference=workflow)

    def create_reference_voice(self,request):
        with self.store.lock:
            ref=self.store.get('references',request.reference_id)
            if ref.get('deleted_at'):raise ValueError('参考已在回收站，请先恢复')
            if not ref['rights_confirmed']:raise ValueError('请先确认录音用途授权，再保存为人物参考')
            voice=self.store.get('voices',request.voice_id) if request.voice_id else None
            if voice and voice.get('deleted_at'):raise ValueError('人物已在回收站，请先恢复')
            if voice and voice['status']=='archived':raise ValueError('该人物已归档，请先恢复人物')
            if ref.get('recording_id'):self.platform.references.save(ref['recording_id'],[ref['id']])
            if voice:
                body={key:voice[key] for key in VoiceInput.model_fields if key in voice}
                body['reference_ids']=list(dict.fromkeys(voice.get('reference_ids',[])+[voice.get('reference_id'),ref['id']]))
                body['reference_ids']=[i for i in body['reference_ids'] if i]
                body['reference_id']=voice.get('reference_id') or ref['id']
                body['reference_scenarios']={**voice.get('reference_scenarios',{}),ref['id']:request.scenario or '备选参考'}
                return self.platform.create_voice(VoiceInput(**body),voice['id'])
            return self.platform.create_voice(VoiceInput(name=request.name,reference_id=ref['id'],reference_ids=[ref['id']],description='由参考整理创建，待试听确认；保留来源、原录音与处理链',status='draft',reference_confirmed=False))
