"""Non-destructive restoration queue and the one-upload smart reference workflow."""
import copy
import hashlib
import json
import logging
import threading
from pathlib import Path
import soundfile as sf
from .audio import sha256
from .schemas import ProcessingInput,VoiceInput
from .store import uid,now
from .worker_runner import run_worker,run_command
from .tracking_quality import reference_quality
from .processing_readiness import snapshots,readiness

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
        tracking=self.config.get('speaker_tracking',{})
        model=Path(tracking.get('model_dir','models/pyannote-community-1'))
        python=Path(tracking.get('python','runtime/diarization-env/Scripts/python.exe'))
        model=model if model.is_absolute() else Path(self.config['root'])/model
        python=python if python.is_absolute() else Path(self.config['root'])/python
        models.append(dict(operation='track_speakers',label='按人物整理',
            available=self.options.get('enabled',False) and (model/'provenance.json').is_file() and python.is_file(),
            note='全程人物标注、独白筛选；最多两路重叠单独分离，模糊归属保留待确认'))
        return dict(enabled=self.options.get('enabled',False),device=self.options.get('device'),operations=models,
                    stages=readiness(self.config),originals_preserved=True)

    def _existing_request(self,key,request):
        if not key:return None,None
        if len(key)>200:raise ValueError('幂等键过长')
        fingerprint=hashlib.sha256(json.dumps(request.model_dump(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.store.connect() as db:
            row=db.execute("SELECT body FROM entities WHERE kind='audio_processing' AND json_extract(body,'$.idempotency_key')=?",(key,)).fetchone()
        if row:
            item=json.loads(row[0])
            if item.get('request_fingerprint')!=fingerprint:raise ValueError('同一幂等键已用于不同内容')
            if item.get('deleted_at'):raise ValueError('任务已在回收站，请先恢复')
            return item,fingerprint
        return None,fingerprint

    def submit(self,request,workflow_root=None,key=None):
        if self.platform.shutdown.is_set():raise ValueError('服务正在停止，请重新启动后提交')
        if not self.options.get('enabled'):raise ValueError('音频处理未启用')
        with self.store.lock:
            existing,fingerprint=self._existing_request(key,request)
            if existing:return existing
            if self.store.by_status('audio_processing',['queued','running','cancel_requested'],count=True)>=self.options['max_pending']:raise ValueError('音频处理队列已满，请稍后再试')
            source=self.store.get('recordings',request.recording_id)
            if source.get('deleted_at'):raise ValueError('录音已在回收站，请先恢复')
            available={c['operation'] for c in self.capabilities()['operations'] if c['available']}
            if set(request.operations)-available:raise ValueError('所选处理模型尚未完整安装')
            if source['status'] not in TERMINAL:raise ValueError('请等待原录音时长与分析完成')
            item=dict(id=uid(),recording_id=source['id'],root_recording_id=source.get('root_recording_id',source['id']),
                source_snapshot=copy.deepcopy(source),operations=request.operations,analyze_outputs=request.analyze_outputs,
                workflow_root=workflow_root,status='queued',progress=0,message='等待处理；原件保留',outputs=[],child_recording_ids=[],import_errors=[],created_at=now(),error=None)
            item['speaker_count']=request.speaker_count
            if key:item.update(idempotency_key=key,request_fingerprint=fingerprint)
            if request.source_processing_id:
                item['source_processing_id']=request.source_processing_id
                parent=self.store.get('audio_processing',request.source_processing_id)
                if parent.get('deleted_at') or parent['status']!='succeeded' or parent['recording_id']!=source['id']:
                    raise ValueError('请选择同一录音已完成的处理结果')
                cleaned=next((o for o in parent['outputs'] if o['stage']=='remove_music' and o['role']=='speech'),None)
                if cleaned:item['tracking_source']=dict(cleaned,source_processing_id=parent['id'])
            item['options_snapshot']=copy.deepcopy(self.options)
            if request.operations==['track_speakers']:
                item['tracking_options_snapshot']=copy.deepcopy(self.config['speaker_tracking'])
                item['tracking_model_snapshots']=snapshots(self.config,freeze_vad=True)
            item['model_snapshots']={}
            for operation in request.operations:
                if operation=='track_speakers':continue
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
        # Assembly reads selected immutable clips, never the full original recording.
        source=None if item.get('assembly_inputs') else self._decode(item,folder)
        if item.get('assembly_inputs'):
            original=self.data/item['source_snapshot']['original_path']
            if sha256(original)!=item['source_snapshot']['original_sha256']:raise ValueError('来源录音哈希不匹配')
            parent=self.store.get('audio_processing',item['source_processing_id'])
            if parent.get('deleted_at'):raise ValueError('来源处理记录已在回收站')
            if item.get('purpose')=='reference' and parent.get('tracking',{}).get('revision',1)!=item['source_revision']:
                raise ValueError('来源片段已变化，请重新选择')
        config=copy.deepcopy(self.config);config['audio_processing']=item['options_snapshot']
        if item.get('tracking_options_snapshot'):config['speaker_tracking']=item['tracking_options_snapshot']
        for key,expected in item['model_snapshots'].items():
            path=Path(item['options_snapshot'][key]);path=path if path.is_absolute() else Path(self.config['root'])/path
            if json.loads((path/'provenance.json').read_text(encoding='utf-8'))!=expected:raise ValueError('模型版本已变化，请新建处理任务；原件保留')
        use_gpu=item['options_snapshot']['device'].startswith('cuda') and not item.get('assembly_inputs');acquired=False
        try:
            if use_gpu:
                while not acquired:
                    if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，原件保留')
                    acquired=self.platform.engine_lock.acquire(timeout=.5)
                if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，原件保留')
                self.platform.unload()  # RLock: release the TTS weights before this owned GPU worker loads its models.
            tracked=item['operations']==['track_speakers']
            if tracked and item.get('tracking_source'):
                source=self.data/item['tracking_source']['path']
                if sha256(source)!=item['tracking_source']['sha256']:raise ValueError('去音乐输入校验失败，原件保留')
            request=dict(mode='track' if tracked else 'process',input_path=str(source),
                speaker_count=item.get('speaker_count'),operations=item['operations'],config_snapshot=config,
                tracking_model_snapshots=item.get('tracking_model_snapshots',{}))
            if item.get('assembly_inputs'):
                request.update(mode='assemble',assembly_inputs=item['assembly_inputs'],assembly_name=item['assembly_name'],
                    gap_ms=item['gap_ms'],assembly_models=item['assembly_models'],purpose=item.get('purpose','audition'),
                    reference_qc=item.get('reference_qc'))
            result=self._run_worker(request,folder,'audio_processing',item['id'])
            if self.stop_event.is_set() or self.store.get('audio_processing',item['id'])['status']=='cancel_requested':raise InterruptedError('处理已停止，已有文件保留')
        finally:
            if acquired:self.platform.engine_lock.release()
        outputs=[]
        for output in result['outputs']:
            path=Path(output.pop('file')).resolve()
            path.relative_to(folder.resolve())
            output=dict(output,id=uid(),path=str(path.relative_to(self.data)),processing_id=item['id'],recording_id=None)
            outputs.append(output)
        extra=dict(tracking=dict(result['tracking'],revision=1)) if 'tracking' in result else {}
        partial=bool(extra.get('tracking',{}).get('unresolved'))
        self.store.update('audio_processing',item['id'],status='succeeded',completeness='partial' if partial else 'complete',outputs=outputs,progress=100,message=('部分片段待确认；可靠结果可继续使用' if partial else '人物整理完成，请试听并命名') if extra else '处理完成，可比较原件与各个结果',model_sources=result['model_sources'],device=result['device'],note=result['note'],finished_at=now(),**extra)
        if extra:return
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
            if output.get('reference_eligible') is False:raise ValueError('请使用独立片段，或试听确认后保存复合参考草稿')
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

    def name_speaker(self,identity,speaker_id,name):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item.get('deleted_at'):raise ValueError('处理记录已在回收站，请先恢复')
            tracking=copy.deepcopy(item.get('tracking',{}))
            speaker=next((s for s in tracking.get('speakers',[]) if s['id']==speaker_id),None)
            if not speaker:raise KeyError('人物不存在')
            speaker['name']=name
            # A run-local name never changes another run or an existing voice automatically.
            for output in item['outputs']:
                if output.get('speaker_id')==speaker_id and output.get('reference_id'):
                    reference=self.store.get('references',output['reference_id'])
                    if not reference.get('deleted_at'):
                        self.store.update('references',reference['id'],speaker_name=name)
            return self.store.update('audio_processing',identity,tracking=tracking)

    def assemble(self,identity,request,key=None):
        with self.store.lock:
            existing,fingerprint=self._existing_request(key,request)
            if existing:
                if existing.get('source_processing_id')!=identity:raise ValueError('幂等键不属于此来源任务')
                return existing
            if self.platform.shutdown.is_set():raise ValueError('服务正在停止，请重新启动后提交')
            if self.store.by_status('audio_processing',['queued','running','cancel_requested'],count=True)>=self.options['max_pending']:
                raise ValueError('音频处理队列已满，请稍后再试')
            parent=self.store.get('audio_processing',identity)
            source=self.store.get('recordings',parent['recording_id'])
            if parent.get('deleted_at') or source.get('deleted_at') or parent['status']!='succeeded':
                raise ValueError('请选择已完成的人物整理，或先恢复原录音')
            outputs={o['id']:o for o in parent['outputs']}
            chosen=[outputs.get(i) for i in dict.fromkeys(request.output_ids)]
            if any(o is None or o.get('kind')!='clip' for o in chosen):raise ValueError('请选择本次整理的独立语音片段')
            revision=parent.get('tracking',{}).get('revision',1)
            if request.expected_revision is not None and request.expected_revision!=revision:
                raise ValueError('片段归属已更新，请刷新后重新选择')
            qc=reference_quality(chosen,self.config['speaker_tracking'],request.speaker_confirmed,source['rights_confirmed'])
            qc['file_seconds']+=(len(chosen)-1)*request.gap_ms/1000
            if qc['file_seconds']>self.config['speaker_tracking']['reference_max_seconds']:
                qc['issues'].append('参考总时长含间隔超过上限，请减少片段或间隔')
            if request.purpose=='reference' and qc['issues']:raise ValueError('；'.join(qc['issues']))
            for output in chosen:
                if sha256(self.data/output['path'])!=output['sha256']:raise ValueError('所选片段校验失败')
            inputs=[dict(o,file=str(self.data/o['path'])) for o in chosen]
            item=dict(id=uid(),recording_id=source['id'],root_recording_id=parent['root_recording_id'],
                source_snapshot=copy.deepcopy(source),source_processing_id=identity,operations=['assemble_clips'],
                assembly_inputs=inputs,assembly_name=request.name,gap_ms=request.gap_ms,assembly_models=parent['model_sources'],
                purpose=request.purpose,speaker_confirmed=request.speaker_confirmed,source_revision=revision,reference_qc=qc,
                analyze_outputs=False,options_snapshot=copy.deepcopy(self.options),model_snapshots={},
                status='queued',progress=0,message='等待合并所选片段',outputs=[],child_recording_ids=[],import_errors=[],created_at=now(),error=None)
            if key:item.update(idempotency_key=key,request_fingerprint=fingerprint)
            self.store.save('audio_processing',item);self.wake.set();return item

    def assign_clip(self,identity,output_id,request):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item.get('deleted_at') or item['status']!='succeeded':raise ValueError('请先完成或恢复人物整理')
            revision=item.get('tracking',{}).get('revision',1)
            if request.expected_revision!=revision:raise ValueError('片段归属已更新，请刷新后重试')
            if request.speaker_id and request.speaker_id not in {p['id'] for p in item['tracking']['speakers']}:
                raise ValueError('请选择本次录音中的人物，或保持未知')
            output=next((o for o in item['outputs'] if o['id']==output_id and o.get('kind')=='clip'),None)
            if not output:raise KeyError('独立片段不存在')
            history=output.setdefault('assignment_history',[])
            history.append(dict(speaker_id=output.get('speaker_id'),confirmed=output.get('assignment_confirmed',False),
                excluded=output.get('excluded',False),revision=revision,reason=request.reason,changed_at=now()))
            output.update(speaker_id=request.speaker_id,assignment_confirmed=request.confirmed and bool(request.speaker_id),
                          excluded=request.excluded,revision=output.get('revision',1)+1)
            tracking=item['tracking'];tracking['revision']=revision+1
            tracking['timelines_stale']=True
            # Immutable derived audio and voice snapshots remain as generated. Mark provenance drift.
            for child in self.store.list('audio_processing'):
                if child.get('source_processing_id')==identity and child.get('assembly_inputs'):
                    self.store.update('audio_processing',child['id'],source_changed=True)
            for reference in self.store.list('references'):
                if reference.get('processing_id')==identity or reference.get('source_lineage',{}).get('tracking_id')==identity:
                    self.store.update('references',reference['id'],source_changed=True)
            return self.store.update('audio_processing',identity,outputs=item['outputs'],tracking=tracking)

    def save_composite(self,identity,request):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item.get('deleted_at') or item['status']!='succeeded' or item.get('purpose')!='reference':
                raise ValueError('请选择已完成的复合参考草稿')
            if not request.listened:raise ValueError('请先试听合并结果并确认人物声音一致')
            parent=self.store.get('audio_processing',item['source_processing_id'])
            source=self.store.get('recordings',item['recording_id'])
            if parent.get('deleted_at') or source.get('deleted_at'):raise ValueError('请先恢复来源录音与处理记录')
            if item.get('source_changed') or parent['tracking'].get('revision',1)!=item['source_revision']:
                raise ValueError('来源片段归属已变化，请重新创建复合参考；旧音频保留')
            output=item['outputs'][0]
            if item.get('reference_id'):
                ref=self.store.get('references',item['reference_id'])
                if ref.get('deleted_at'):raise ValueError('参考在回收站，请先恢复')
                return ref
            if not source['rights_confirmed']:raise ValueError('原录音尚未确认使用授权')
            if sha256(self.data/output['path'])!=output['sha256']:raise ValueError('复合参考音频校验失败')
            speaker_id=item['assembly_inputs'][0]['speaker_id']
            person=next(p for p in parent['tracking']['speakers'] if p['id']==speaker_id)
            mapped=[span for c in item['assembly_inputs'] for span in c['source_spans']]
            reference=dict(id=uid(),reference_kind='composite',revision=1,name=request.name,scenario=request.scenario,
                notes='',tags=[],speaker_name=person['name'] or speaker_id,speaker_id=speaker_id,
                speaker_binding=dict(tracking_id=parent['id'],speaker_id=speaker_id,confirmed=True),
                recording_id=source['id'],processing_id=identity,processing_output_id=output['id'],
                original_name=source['original_name'],path=output['path'],sha256=output['sha256'],sample_rate=output['sample_rate'],
                duration=output['duration'],start=min(s['source_start'] for s in mapped),end=max(s['source_end'] for s in mapped),
                source_spans=mapped,source_map=output['source_spans'],
                component_refs=[dict(output_id=c['id'],sha256=c['sha256'],revision=c.get('revision',1),source_spans=c['source_spans']) for c in item['assembly_inputs']],
                qc=item['reference_qc'],original_path=source['original_path'],original_sha256=source['original_sha256'],
                source=source['source'],authorization=source['authorization'],rights_confirmed=True,
                saved=True,saved_at=now(),created_at=now(),transcript=output['transcript'],transcript_history=[],
                embedding=output['embedding'],speaker_labels=[speaker_id],review='pending',
                quality=dict(score_source='not_scored',warnings=['复合参考需试听，转写需校对']),
                analysis_models=item['model_sources'],source_lineage=dict(tracking_id=parent['id'],source_revision=item['source_revision']))
            self.store.save('references',reference)
            self.store.update('recordings',source['id'],candidate_ids=source['candidate_ids']+[reference['id']])
            self.store.update('audio_processing',identity,reference_id=reference['id'])
            return reference

    def save_tracked(self,identity,output_ids,scenario=''):
        with self.store.lock:
            item=self.store.get('audio_processing',identity)
            if item.get('deleted_at') or item['status']!='succeeded':raise ValueError('请等待人物整理完成，或先恢复处理记录')
            source=self.store.get('recordings',item['recording_id'])
            if source.get('deleted_at'):raise ValueError('原录音已在回收站，请先恢复')
            outputs={o['id']:o for o in item['outputs']}
            chosen=[outputs.get(o) for o in dict.fromkeys(output_ids)]
            if any(o is None or o.get('kind')!='clip' for o in chosen):raise ValueError('只可保存本次整理的独立参考片段')
            profiles={s['id']:s for s in item['tracking']['speakers']}
            for o in chosen:
                if not o.get('speaker_id'):raise ValueError('人物归属不明确，请先选择其他明确归属的片段')
                if o.get('excluded'):raise ValueError('已排除片段不能保存为人物参考')
                if o['duration']<.5:raise ValueError('短于 0.5 秒的片段仅供试听或手动合并，请选择较长片段作为参考')
                if o.get('reference_id') and self.store.get('references',o['reference_id']).get('deleted_at'):
                    raise ValueError('已保存的片段在回收站，请先恢复')
                if sha256(self.data/o['path'])!=o['sha256']:raise ValueError('参考片段校验失败')
            references=[];candidate_ids=list(source['candidate_ids'])
            for o in chosen:
                if o.get('reference_id'):
                    reference=self.store.get('references',o['reference_id'])
                    if reference.get('deleted_at'):raise ValueError('已保存的片段在回收站，请先恢复')
                    references.append(reference);continue
                speaker=profiles[o['speaker_id']];name=speaker['name'] or speaker['id']
                span=o['source_spans'][0]
                reference=dict(id=uid(),name=f'{name} · {span["source_start"]:.1f}–{span["source_end"]:.1f}s',
                    speaker_name=name,speaker_id=speaker['id'],scenario=scenario,notes='',tags=[],
                    recording_id=source['id'],processing_id=identity,processing_output_id=o['id'],
                    original_name=source['original_name'],path=o['path'],sha256=o['sha256'],sample_rate=o['sample_rate'],
                    duration=o['duration'],start=span['source_start'],end=o['source_spans'][-1]['source_end'],source_spans=o['source_spans'],
                    original_path=source['original_path'],original_sha256=source['original_sha256'],
                    source=source['source'],authorization=source['authorization'],rights_confirmed=source['rights_confirmed'],
                    saved=True,saved_at=now(),created_at=now(),transcript=o['transcript'],transcript_history=[],
                    embedding=o['embedding'],speaker_labels=[speaker['id']],review='pending',
                    quality=dict(score_source='not_scored',origin=o['origin'],warnings=o.get('warnings',[])),
                    analysis_models=item['model_sources'],source_lineage=dict(tracking_id=identity,origin=o['origin'],similarity=o.get('similarity')))
                self.store.save('references',reference);o['reference_id']=reference['id']
                candidate_ids.append(reference['id']);references.append(reference)
            self.store.update('recordings',source['id'],candidate_ids=candidate_ids)
            self.store.update('audio_processing',identity,outputs=item['outputs'])
            return references

    def _work(self):
        while not self.stop_event.is_set():
            self.advance_workflows()
            queued=self.store.by_status('audio_processing',['queued'],limit=1)
            if not queued:self.wake.wait(.7);self.wake.clear();continue
            item=queued[0]
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
        for recording in self.store.active_reference_workflows():
            workflow=recording.get('smart_reference')
            if not workflow or workflow['status'] in {'ready','partial','failed','cancelled'}:continue
            try:
                if recording['status'] in {'failed','cancelled'}:
                    self._workflow(recording,dict(workflow,status='failed',message='原录音仍保留，请重试分析或进入高级处理'));continue
                if recording['status']!='succeeded':continue
                if not workflow.get('processing_id'):
                    # Prefer original speech. Only uncertain/flagged stages get alternatives.
                    if readiness(self.config)['solo_references']:
                        operations=['track_speakers']
                    else:
                        summary=recording.get('summary',{})
                        operations=[]
                        if summary.get('music_suspected'):operations.append('remove_music')
                        if summary.get('noise_suspected'):operations.append('denoise')
                        if not operations:
                            self._workflow(recording,dict(workflow,status='ready',message='原声候选已准备，请试听选择',recommendations=self.recommendations(self.candidates(recording))))
                            continue
                    task=self.submit(ProcessingInput(recording_id=recording['id'],operations=operations),workflow_root=recording['id'])
                    self._workflow(recording,dict(workflow,status='processing',processing_id=task['id'],message='正在自动分离与整理，原件候选同时保留'));continue
                task=self.store.get('audio_processing',workflow['processing_id'])
                if task['status'] not in TERMINAL:continue
                if task['operations']==['track_speakers']:
                    self._workflow(recording,dict(workflow,status='partial' if task['status']!='succeeded' or task.get('completeness')=='partial' else 'ready',
                        tracking_id=task['id'],message='人物片段已整理，请试听确认并保存参考',recommendations=[]))
                    continue
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
            selected=list(dict.fromkeys([request.reference_id,*request.reference_ids]))
            if len(selected)>40:raise ValueError('每个人物最多保存 40 个参考')
            for identity in selected:
                candidate=self.store.get('references',identity)
                if candidate.get('deleted_at') or not candidate['rights_confirmed']:
                    raise ValueError('所选参考已删除或缺少授权确认')
            for identity in selected:
                candidate=self.store.get('references',identity)
                if candidate.get('recording_id'):self.platform.references.save(candidate['recording_id'],[identity])
            if voice:
                body={key:voice[key] for key in VoiceInput.model_fields if key in voice}
                body['reference_ids']=list(dict.fromkeys(voice.get('reference_ids',[])+[voice.get('reference_id')]+selected))
                body['reference_ids']=[i for i in body['reference_ids'] if i]
                body['reference_id']=voice.get('reference_id') or ref['id']
                body['reference_scenarios']={**voice.get('reference_scenarios',{}),**{i:request.scenario or '备选参考' for i in selected}}
                return self.platform.create_voice(VoiceInput(**body),voice['id'])
            return self.platform.create_voice(VoiceInput(name=request.name,reference_id=ref['id'],reference_ids=selected,
                reference_scenarios={i:request.scenario for i in selected if request.scenario},
                description='由参考录音创建',status='draft',reference_confirmed=False))
