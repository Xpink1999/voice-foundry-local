import copy
import importlib.metadata
import json
import logging
import os
import secrets
import shutil
import string
import threading
import time
import zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
import soundfile as sf
from .audio import sha256, split_text, write_wav, write_srt, safe_name, convert_audio, join_wavs
from .engines import build_engines, resolve
from .schemas import GenerationInput
from .store import Store, uid, now
from .references import ReferenceLibrary
from .restoration import AudioRestoration
from .longform import Longform
from .assets import Assets

log = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}

class Cancelled(Exception):
    pass

class Platform:
    def __init__(self, config):
        self.config = config
        self.data = Path(config["data_dir"])
        self.store = Store(self.data)
        self.engines = build_engines(config)
        self.engine_lock = threading.RLock()
        self.wake = threading.Event()
        self.shutdown = threading.Event()
        self.worker = None
        self.active_engine = None
        self.last_use = time.monotonic()
        self.loaded_at = None
        self.runtime = {}
        self.references = ReferenceLibrary(self)
        self.restoration = AudioRestoration(self)
        self.longform = Longform(self)
        self.assets = Assets(self)
        self.last_archive_check = 0

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        for job in self.store.list("jobs"):
            if job["status"] == "running":
                # Existing partial outputs remain inspectable; never silently overwrite a run.
                self.store.update("jobs", job["id"], status="failed", error="服务中断；已保留部分输出，可创建重试任务", finished_at=now())
                self.store.event(job["id"], "interrupted")
            elif job["status"] == "cancel_requested":
                self.store.update("jobs", job["id"], status="cancelled", finished_at=now())
        for package in ("voice-foundry-local", "torch", "torchaudio", "transformers", "numpy", "librosa"):
            try:
                self.runtime[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                self.runtime[package] = "not-installed"
        self.shutdown.clear()
        self.archive_due(force=True)
        self.worker = threading.Thread(target=self._work, name="voice-worker", daemon=True)
        self.worker.start()
        self.references.start()
        self.restoration.start()
        self.longform.start()

    def stop(self):
        self.request_stop()
        self.longform.stop()
        self.restoration.stop()
        self.references.stop()
        if self.worker:
            self.worker.join(timeout=10)
        self.unload()

    def request_stop(self):
        self.shutdown.set()
        self.wake.set()
        for producer in (self.longform, self.restoration, self.references):
            producer.stop_event.set()
            producer.wake.set()
        for engine in self.engines.values():
            interrupt = getattr(engine, 'interrupt', None)
            if interrupt:
                interrupt()

    def models(self):
        return [dict(id=k, label=self.config["engines"][k].get("label", k), loaded=k == self.loaded_engine(),
                     capabilities=e.capabilities(), identity=e.identity()) for k, e in self.engines.items()]

    def loaded_engine(self):
        identity = self.active_engine
        return identity if identity and getattr(self.engines[identity], 'loaded', True) else None

    def engine_process_ids(self):
        return [pid for engine in self.engines.values() if (pid := getattr(engine, 'pid', None)) is not None]

    def unload(self):
        if not self.engine_lock.acquire(blocking=False):
            raise ValueError("任务正在生成，请取消或等候完成后释放显存")
        try:
            if self.active_engine:
                self.engines[self.active_engine].unload()
            self.active_engine = None
            self.loaded_at = None
        finally:
            self.engine_lock.release()

    def load_engine(self, identity):
        with self.engine_lock:
            engine = self.engines[identity]
            if self.loaded_engine() == identity:
                return engine
            self.unload()
            try:
                engine.load()
            except Exception:
                try:
                    engine.unload()
                except Exception:
                    log.exception('cleanup after model load failure: %s', identity)
                raise
            self.active_engine = identity
            self.loaded_at = now()
            return engine

    def create_project(self, request):
        return self.store.save("projects", dict(request.model_dump(), id=uid(), created_at=now()))

    def create_voice(self, request, voice_id=None):
        values = request.model_dump()
        values["engine"] = values["engine"] or self.config["default_engine"]
        if values["engine"] not in self.engines:
            raise ValueError("未知语音引擎")
        if values["project_id"]:
            project=self.store.get("projects", values["project_id"])
            if project.get("deleted_at"):raise ValueError("项目已在回收站，请先恢复")
        reference = self.store.get("references", values["reference_id"]) if values["reference_id"] else None
        ids=list(dict.fromkeys(([values['reference_id']] if values['reference_id'] else [])+values['reference_ids']))
        references=[self.store.get('references',r) for r in ids]
        if any(r.get('deleted_at') for r in references):raise ValueError('参考已在回收站，请先恢复')
        if any(not r['rights_confirmed'] for r in references):raise ValueError('参考音频尚未确认使用授权')
        if any(not r.get('saved',True) for r in references):raise ValueError('请先试听选择并保存候选片段')
        if set(values['reference_scenarios'])-set(ids):raise ValueError('场景标签必须属于该人物的参考集合')
        values['reference_ids']=ids
        if values["reference_confirmed"] and not reference:
            raise ValueError("确认参考前需要上传参考音频")
        if values["status"] == "active" and not values["reference_confirmed"]:
            raise ValueError("正式音色需要明确确认的参考音频；请先保存为草稿并试听")
        if values["sample_result_id"]:
            sample = self.store.get("results", values["sample_result_id"])
            if sample["engine"] != values["engine"]:
                raise ValueError("示例音频与音色引擎不匹配")
            if not values["engine_options"]:
                values["engine_options"] = copy.deepcopy(sample["parameters"].get("engine_options", {}))
        if reference and not self.engines[values["engine"]].capabilities().get("cloning"):
            raise ValueError("该引擎不支持参考克隆")
        validated = self.prepare_job(GenerationInput(text="音色参数校验", engine=values["engine"], engine_options=values["engine_options"], style=values["style"]))
        values["engine_options"] = validated["request"]["engine_options"]
        with self.store.lock:
            previous = self.store.get("voices", voice_id) if voice_id else None
            if previous and previous.get("deleted_at"):raise ValueError("人物已在回收站，请先恢复")
            version = (previous["version"] + 1) if previous else 1
            item = dict(values, id=voice_id or uid(), version=version, created_at=previous["created_at"] if previous else now(), updated_at=now(),
                        reference=reference, references=references, model=self.engines[values["engine"]].identity())
            self.store.save("voice_versions", dict(copy.deepcopy(item), id=f"{item['id']}:{version}", voice_id=item["id"]))
            return self.store.save("voices", item)

    def upload_reference(self, filename, content, source, authorization, rights_confirmed):
        if len(content) > self.config["max_upload_mb"] * 1024 * 1024:
            raise ValueError("上传音频超过大小限制")
        if not source.strip() or not authorization.strip():
            raise ValueError("必须填写来源与授权说明")
        identity = uid()
        folder = self.data / "references" / identity
        folder.mkdir(parents=True)
        original = folder / ("original" + (Path(filename).suffix.lower() if Path(filename).suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a"} else ".audio"))
        original.write_bytes(content)
        try:
            info = sf.info(original)
            if not 0.5 <= info.duration <= 90 or info.channels > 8:
                raise ValueError("旧版直接参考需为 0.5–90 秒，推荐 5–30 秒；长录音请使用自动预处理上传")
            pcm, rate = sf.read(original, dtype="float32", always_2d=True)
            normalized = folder / "reference.wav"
            write_wav(normalized, pcm.mean(axis=1), rate)
        except Exception:
            shutil.rmtree(folder)
            raise ValueError("无法解码参考音频，或音频不符合时长/声道限制；请使用 WAV/FLAC/MP3/OGG")
        return self.store.save("references", dict(id=identity, original_name=safe_name(filename), path=str(normalized.relative_to(self.data)),
                    original_path=str(original.relative_to(self.data)), sha256=sha256(normalized), original_sha256=sha256(original),
                    source=source.strip(), authorization=authorization.strip(), rights_confirmed=rights_confirmed,
                    duration=info.duration, sample_rate=rate, created_at=now()))

    def prepare_job(self, request, batch_id=None, retry_of=None):
        values = request.model_dump()
        if len(values["text"]) > self.config["max_text_chars"]:
            raise ValueError("文本超出配置长度上限")
        if values["project_id"]:
            project=self.store.get("projects", values["project_id"])
            if project.get("deleted_at"):raise ValueError("项目已在回收站，请先恢复")
        voice = self.store.get("voices", values["voice_id"]) if values["voice_id"] else None
        if voice:
            if voice.get("deleted_at"):raise ValueError("人物已在回收站，请先恢复")
            if voice["status"] == "archived":
                raise ValueError("音色已归档")
            if voice["project_id"] and voice["project_id"] != values["project_id"]:
                raise ValueError("项目专属音色不可跨项目使用；请先主动共享音色")
            engine_id = values["engine"] or voice["engine"]
            if engine_id != voice["engine"]:
                raise ValueError("音色与引擎不匹配；请选择同一引擎或建立新音色")
        else:
            engine_id = values["engine"] or self.config["default_engine"]
        if engine_id not in self.engines:
            raise ValueError("未知语音引擎")
        chosen_reference=values['reference_id'] or (voice.get('reference_id') if voice else None)
        reference=self.store.get('references',chosen_reference) if chosen_reference else None
        if reference and reference.get('deleted_at'):raise ValueError('参考已在回收站，请先恢复')
        if reference and (not reference['rights_confirmed'] or not reference.get('saved',True)):
            raise ValueError('参考片段未保存或使用授权尚未确认')
        caps = self.engines[engine_id].capabilities()
        parameter_specs = caps.get("parameters", {})
        options = {**(voice.get("engine_options", {}) if voice else {}), **values["engine_options"]}
        values["engine_options"] = options
        if options.keys() - parameter_specs.keys():
            raise ValueError("引擎不支持这些参数: " + ", ".join(sorted(options.keys() - parameter_specs.keys())))
        for key, spec in parameter_specs.items():
            value = options.get(key, spec.get("default"))
            kind = spec.get("type", "string")
            if kind in {"number", "integer"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
                    raise ValueError(f"引擎参数 {key} 需要数字")
                if kind == "integer" and not isinstance(value, int):
                    raise ValueError(f"引擎参数 {key} 需要整数")
                if value < spec.get("min", -float("inf")) or value > spec.get("max", float("inf")):
                    raise ValueError(f"引擎参数 {key} 超出允许范围")
            elif kind == "boolean" and not isinstance(value, bool):
                raise ValueError(f"引擎参数 {key} 需要布尔值")
            elif kind == "string" and not isinstance(value, str):
                raise ValueError(f"引擎参数 {key} 需要字符串")
            if "enum" in spec and value not in spec["enum"]:
                raise ValueError(f"引擎参数 {key} 不是允许的选项")
            options[key] = value
        style = ", ".join(filter(None, [voice.get("style", "") if voice else "", values["style"]]))
        control_note=None
        if values['clone_mode']=='hifi':
            if not caps.get('hifi_cloning'):raise ValueError('该模型不支持 Hi-Fi 延续式克隆')
            if not reference or not reference.get('transcript',{}).get('text','').strip():raise ValueError('Hi-Fi 模式需要所选片段的转写文本，请先自动转写或校对填写')
            if not caps.get('hifi_style_control',False):
                if values['style']:raise ValueError('此模型的 Hi-Fi 沿用参考演绎，不支持额外声音描述；请清空描述或选择参考克隆模式')
                style='';control_note='Hi-Fi 沿用参考演绎；未使用人物的默认声音描述，避免被朗读'
        if values["streaming"] and not caps.get("streaming"):
            raise ValueError("该模型不支持流式生成")
        if style and not caps.get("voice_design"):
            raise ValueError("该模型不支持自然语言声音设计")
        if reference and not caps.get("cloning"):
            raise ValueError("该模型不支持声音克隆")
        if values["language"] != "auto" and values["language"] not in caps.get("languages", []):
            raise ValueError("该模型未声明支持此语言")
        seed = values["seed"] if values["seed"] is not None else voice["seed"] if voice else secrets.randbelow(2147483647)
        if seed + values["candidates"] > 2147483647:
            raise ValueError("种子接近上限，无法分配候选种子")
        return dict(id=uid(), request=values, text=values["text"], title=values["title"], project_id=values["project_id"],
                    engine=engine_id, model=copy.deepcopy(self.engines[engine_id].identity()), voice_snapshot=copy.deepcopy(voice), reference_snapshot=copy.deepcopy(reference),
                    style=style, seed=seed, status="queued", progress=0, batch_id=batch_id, retry_of=retry_of,
                    attempt=0, results=[], error=None, created_at=now(), runtime=copy.deepcopy(self.runtime),
                    pipeline={**{key: self.config[key] for key in ("segment_chars", "segment_pause_ms")},'control_note':control_note})

    def submit(self, requests, batch=False):
        if self.shutdown.is_set():
            raise ValueError('Service is stopping; start it again before submitting tasks.')
        with self.store.lock:
            pending = sum(j["status"] in {"queued", "running", "cancel_requested"} for j in self.store.list("jobs"))
            if pending + len(requests) > self.config["max_pending_jobs"]:
                raise ValueError("队列已满，请稍后重试")
            batch_id = uid() if batch else None
            jobs = [self.prepare_job(r, batch_id) for r in requests]  # validate all before saving any
            for job in jobs:
                self.store.save("jobs", job)
                self.store.event(job["id"], "queued")
        self.wake.set()
        return jobs

    def retry(self, identity):
        old = self.store.get("jobs", identity)
        if old["status"] not in {"failed", "cancelled"}:
            raise ValueError("只可重试失败或取消的任务")
        # Reuse frozen voice/model/seed, even if the current voice has changed.
        with self.store.lock:
            pending = sum(j["status"] in {"queued", "running", "cancel_requested"} for j in self.store.list("jobs"))
            if pending >= self.config["max_pending_jobs"]:
                raise ValueError("队列已满")
            job = copy.deepcopy(old)
            job.update(id=uid(), status="queued", progress=0, attempt=0, results=[], error=None, retry_of=identity, created_at=now())
            for key in ("finished_at", "started_at", "updated_at", "archived_at", "archive_reason", "archive_history", "restored_at"):
                job.pop(key, None)
            self.store.save("jobs", job)
        self.wake.set()
        return job

    def cancel(self, identity):
        with self.store.lock:
            job = self.store.get("jobs", identity)
            if job["status"] in TERMINAL:
                return job
            changes=dict(status="cancelled" if job["status"] == "queued" else "cancel_requested")
            if job['status']=='queued':changes['finished_at']=now()
            return self.store.update("jobs", identity, **changes)

    def archive_jobs(self, identities, restore=False, reason='manual'):
        with self.store.lock:
            jobs=[self.store.get('jobs',identity) for identity in dict.fromkeys(identities)]
            if any(j['status'] not in TERMINAL for j in jobs):raise ValueError('仅可归档或恢复已完成、失败、取消的任务；运行中及排队任务不会归档')
            changed=[]
            for job in jobs:
                if bool(job.get('archived_at'))==restore:
                    timestamp=now();action='restored' if restore else 'archived'
                    changes=dict(archived_at=None if restore else timestamp,archive_reason=None if restore else reason,
                        archive_history=job.get('archive_history',[])+[dict(action=action,at=timestamp,reason=reason)])
                    if restore:changes['restored_at']=timestamp
                    self.store.update('jobs',job['id'],**changes)
                    self.store.event(job['id'],action,reason=reason);changed.append(job['id'])
            return dict(changed_ids=changed,restored=restore,assets_preserved=True)

    def archive_due(self, force=False, clock=None):
        if not force and time.monotonic()-self.last_archive_check<60:return []
        self.last_archive_check=time.monotonic()
        days=self.config.get('task_archive_after_days',7)
        if not days:return []
        cutoff=(clock or datetime.now(timezone.utc))-timedelta(days=days)
        with self.store.lock:
            due=[]
            for job in self.store.jobs()['items']:
                if job['status'] not in TERMINAL:continue
                try:
                    # A restored task gets a fresh retention period rather than disappearing again immediately.
                    stamp=datetime.fromisoformat(job.get('restored_at') or job.get('finished_at') or job.get('updated_at') or job['created_at'])
                    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
                    if stamp<=cutoff:due.append(job['id'])
                except (ValueError,TypeError):continue
            if due:self.archive_jobs(due,reason='age_policy')
            return due

    def _check_cancel(self, job):
        if self.shutdown.is_set() or self.store.get("jobs", job["id"])["status"] in {"cancel_requested", "cancelled"}:
            raise Cancelled()

    def _work(self):
        while not self.shutdown.is_set():
            self.archive_due()
            jobs = [j for j in self.store.list("jobs") if j["status"] == "queued"]
            if not jobs:
                if self.active_engine and time.monotonic() - self.last_use > self.config["idle_unload_seconds"]:
                    try:self.unload()
                    except ValueError:pass  # Another independent producer currently owns the engine lock.
                self.wake.wait(1)
                self.wake.clear()
                continue
            job = jobs[-1]
            with self.store.lock:
                if self.store.get("jobs", job["id"])["status"] != "queued":
                    continue
                self.store.update("jobs", job["id"], status="running", started_at=now())
            for attempt in range(job["request"]["max_retries"] + 1):
                try:
                    self._check_cancel(job)
                    self.store.update("jobs", job["id"], attempt=attempt + 1)
                    self._generate(job, attempt)
                    self._check_cancel(job)
                    self.store.update("jobs", job["id"], status="succeeded", progress=100, error=None, finished_at=now())
                    self.store.event(job["id"], "succeeded")
                    break
                except Cancelled:
                    self.store.update("jobs", job["id"], status="cancelled", finished_at=now())
                    self.store.event(job["id"], "cancelled")
                    break
                except Exception as error:
                    if self.shutdown.is_set():
                        self.store.update('jobs', job['id'], status='cancelled', finished_at=now())
                        self.store.event(job['id'], 'cancelled')
                        break
                    log.exception("generation failed: %s", job["id"])
                    self.store.event(job["id"], "error", attempt=attempt + 1, message=str(error)[:3000])
                    self.store.update("jobs", job["id"], error=str(error)[:3000])
                    if attempt == job["request"]["max_retries"]:
                        self.store.update("jobs", job["id"], status="failed", finished_at=now())
                    else:
                        self.store.event(job["id"], "retrying")
                finally:
                    self.last_use = time.monotonic()

    def _generate(self, job, attempt):
        engine = self.engines[job["engine"]]
        if engine.identity() != job["model"]:
            raise ValueError("模型版本已变化，拒绝以不同权重执行冻结任务；请创建新任务")
        pipeline = job.get("pipeline", self.config)
        segments = split_text(job["text"], pipeline["segment_chars"])
        request = job["request"]
        voice = job["voice_snapshot"]
        reference = job.get('reference_snapshot',voice.get('reference') if voice else None)
        if reference and sha256(self.data / reference["path"]) != reference["sha256"]:
            raise ValueError("参考音频哈希不匹配")
        with self.engine_lock:
            self._check_cancel(job)
            self.load_engine(job['engine'])
            for candidate in range(request["candidates"]):
                self._check_cancel(job)
                result_id = uid()
                folder = self.data / "originals" / job["id"] / f"attempt-{attempt+1}" / result_id
                folder.mkdir(parents=True)
                total, timeline, parts = 0, [], []
                for index, text in enumerate(segments):
                    self._check_cancel(job)
                    seed = job["seed"] + candidate
                    # Explicitly record per-segment seed rather than hidden RNG state.
                    generation = dict(text=text, style=job["style"], seed=seed,
                        engine_options=request["engine_options"],
                        clone_mode=request.get('clone_mode','reference'),prompt_text=reference.get('transcript',{}).get('text') if reference else None,
                        streaming=request["streaming"], reference_path=str(self.data / reference["path"]) if reference else None)
                    stream = engine.synthesize(generation)
                    chunks = []
                    try:
                        for chunk_index, chunk in enumerate(stream):
                            self._check_cancel(job)
                            chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
                            if request["streaming"]:
                                chunk_path = folder / f"stream-{index:04}-{chunk_index:05}.wav"
                                write_wav(chunk_path, chunk, engine.sample_rate)
                                self.store.event(job["id"], "audio_chunk", result_id=result_id, segment=index, chunk=chunk_index,
                                    path=str(chunk_path.relative_to(self.data)), duration=len(chunk)/engine.sample_rate)
                            chunks.append(chunk)
                    finally:
                        close = getattr(stream, "close", None)
                        if close:
                            close()
                    pcm = np.concatenate(chunks) if chunks else np.array([])
                    write_wav(folder / f"segment-{index+1:04}.wav", pcm, engine.sample_rate)
                    timeline.append(dict(text=text, start=total/engine.sample_rate, end=(total+len(pcm))/engine.sample_rate,
                                         seed=seed, file=f"segment-{index+1:04}.wav"))
                    parts.append(folder / f"segment-{index+1:04}.wav")
                    total += len(pcm)
                    if index < len(segments) - 1:
                        pause = np.zeros(round(pipeline["segment_pause_ms"] * engine.sample_rate / 1000), dtype=np.float32)
                        total += len(pause)
                    self.store.update("jobs", job["id"], progress=round(100*(candidate*len(segments)+index+1)/(request["candidates"]*len(segments)), 1))
                target = folder / "original.wav"
                join_wavs(target, parts, engine.sample_rate, pipeline['segment_pause_ms'], lambda: self._check_cancel(job))
                write_srt(folder / "segments.srt", timeline)
                result = dict(id=result_id, job_id=job["id"], title=job["title"], candidate=candidate+1, attempt=attempt+1,
                    project_id=job["project_id"], voice_snapshot=voice, reference_snapshot=reference, engine=job["engine"], model=job["model"],
                    original_text=job["text"], parameters=dict(request, effective_style=job["style"], effective_seed=job["seed"]+candidate),
                    runtime=job["runtime"], pipeline=job.get("pipeline"), sample_rate=engine.sample_rate, channels=1, duration=total/engine.sample_rate,
                    path=str(target.relative_to(self.data)), sha256=sha256(target), segments=timeline,
                    timestamp_kind="segment_boundaries_not_forced_alignment", review="pending", review_history=[], created_at=now())
                (folder / "provenance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                self.store.save("results", result)
                with self.store.lock:
                    latest = self.store.get("jobs", job["id"])
                    self.store.update("jobs", job["id"], results=latest["results"] + [result_id])
                self.store.event(job["id"], "result", result_id=result_id)

    def review(self, identity, request):
        with self.store.lock:
            result = self.store.get("results", identity)
            entry = dict(request.model_dump(), created_at=now())
            return self.store.update("results", identity, review=request.status, review_history=result["review_history"]+[entry])

    def review_batch(self,request):
        with self.store.lock,self.store.connect() as db:
            stamp=now();items=[]
            for identity in dict.fromkeys(request.result_ids):
                item=self.store.get('results',identity)
                if item.get('deleted_at'):raise ValueError('结果已移入回收站，请先恢复')
                entry=dict(status=request.status,listened=request.listened,note=request.note,reviewer=request.reviewer,created_at=stamp)
                item.update(review=request.status,review_history=item['review_history']+[entry],updated_at=stamp);items.append(item)
            db.executemany("UPDATE entities SET body=? WHERE kind='results' AND id=?",[(json.dumps(item,ensure_ascii=False),item['id']) for item in items])
        return dict(reviewed=len(items),status=request.status)

    def export(self, request):
        values = request.model_dump()
        if request.adapter not in self.config["export_adapters"]:
            raise ValueError("未知导出适配器")
        adapter = resolve(self.config["export_adapters"][request.adapter])()
        results = [self.store.get("results", identity) for identity in request.result_ids]
        if any(r.get("deleted_at") for r in results):raise ValueError("所选结果已在回收站，请先恢复")
        if not request.draft and any(r["review"] != "approved" for r in results):
            raise ValueError("正式导出只允许已人工试听批准的结果；可显式导出草稿")
        if request.trim_silence and request.subtitles:
            raise ValueError("裁剪会改变时间轴；请关闭字幕或关闭静音裁剪，以免输出错位字幕")
        try:
            fields = list(string.Formatter().parse(request.naming))
        except ValueError:
            raise ValueError("无效文件命名规则")
        allowed_fields = {"title", "candidate", "id", "voice_id", "project_id"}
        if any(field is not None and (field not in allowed_fields or spec or conversion) for _, field, spec, conversion in fields):
            raise ValueError("命名规则仅支持 {title} {candidate} {id} {voice_id} {project_id}，不支持格式表达式")
        identity = uid()
        folder = self.data / "exports" / identity
        folder.mkdir(parents=True)
        entries = []
        for result in results:
            source = self.data / result["path"]
            if sha256(source) != result["sha256"]:
                raise ValueError("原始音频哈希不匹配，已停止导出")
            try:
                name = safe_name(request.naming.format(title=safe_name(result["title"]), candidate=result["candidate"],
                    id=result["id"][:8], voice_id=result["voice_snapshot"]["id"] if result["voice_snapshot"] else "narrator", project_id=result["project_id"] or "independent"))
            except (KeyError, ValueError, AttributeError, IndexError):
                raise ValueError("命名规则仅支持 {title} {candidate} {id} {voice_id} {project_id}")
            relative_folder = adapter.folder(result)
            if relative_folder.is_absolute() or ".." in relative_folder.parts:
                raise ValueError("导出适配器返回非法目录")
            target_dir = folder / relative_folder
            target_dir.mkdir(parents=True, exist_ok=True)
            name = ("DRAFT_" if request.draft else "") + name + "_" + result["id"][:8]
            target = target_dir / f"{name}.{request.format}"
            convert_audio(source, target, values, self.config["ffmpeg"])
            if request.subtitles:
                write_srt(target_dir / f"{name}.srt", result["segments"])
            metadata = dict(result, export_options=values, exported_sha256=sha256(target), asset_status="draft" if request.draft else "approved")
            target.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            entries.append(dict(result_id=result["id"], file=str(target.relative_to(folder)), sha256=sha256(target), review=result["review"]))
        manifest = dict(id=identity, version=1, created_at=now(), options=values, results=entries,
                        timestamp_note="字幕为真实分段时长边界，不是词级对齐")
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = folder.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            for path in folder.rglob("*"):
                if path.is_file():
                    package.write(path, path.relative_to(folder))
        return self.store.save("exports", dict(manifest, path=str(archive.relative_to(self.data)), sha256=sha256(archive)))

    def backup(self):
        identity = uid()
        directory = self.data / "backups" / identity
        directory.mkdir(parents=True)
        self.store.backup(directory / "platform.sqlite3")
        shutil.copy2(self.config["config_path"], directory / "platform.json")
        return dict(id=identity, created_at=now(), directory=str(directory), includes="配置与数据库；完整恢复还需备份 references、originals、exports 和模型来源清单")

    def update_settings(self, request):
        with self.store.lock:
            path = Path(self.config["config_path"])
            previous = json.loads(path.read_text(encoding="utf-8-sig"))
            backup = self.data / "backups" / f"config-{uid()}.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            values = request.model_dump(exclude_none=True)
            previous.update(values)
            temporary = path.with_suffix(".tmp.json")
            temporary.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
            self.config.update(values)
            self.last_archive_check=0
            return dict(updated=values, backup=str(backup), note="分段设置仅影响新提交任务；已提交任务保留冻结配置")
