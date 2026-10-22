import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .config import load_config, ROOT
from .schemas import ProjectInput, VoiceInput, GenerationInput, BatchInput, ReviewInput, ExportInput, SettingsInput,SaveClipsInput,TranscriptInput,CompareReferencesInput,ArchiveJobsInput,ProcessingInput,ResultRecordingInput,OutputRecordingInput,ReferenceVoiceInput
from .schemas import LongformImportRetry,LongformAction,LongformExportInput,AssetBatch,ReviewBatch
from .assets import KINDS
from .service import Platform, TERMINAL
from .audio import sha256
from . import __version__

def create_app(config=None):
    config = config or load_config()
    platform = Platform(config)

    @asynccontextmanager
    async def lifespan(app):
        # Process lease avoids two workers touching one persistent queue, even on different ports.
        lease = open(Path(config["data_dir"]) / "service.lock", "a+b")
        if lease.tell() == 0:
            lease.write(b"0")
            lease.flush()
        lease.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handler = RotatingFileHandler(Path(config["log_dir"]) / "platform.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger("voice_platform").addHandler(handler)
        platform.start()
        try:
            yield
        finally:
            platform.stop()
            lease.close()
            logging.getLogger("voice_platform").removeHandler(handler)
            handler.close()

    app = FastAPI(title="声场 · 全局语音生产平台", version="1.0.0", lifespan=lifespan,
                  description="独立于游戏引擎和 Codex。异步生成、音色版本、人工审核、无损原件与可追溯导出。")
    app.state.platform = platform

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        host = request.url.hostname
        allowed = set(config.get("allowed_hosts", ["localhost", "127.0.0.1", "::1"])) | {config["host"]}
        if host not in allowed:
            return JSONResponse({"detail": "Host 不在配置允许范围"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "拒绝跨源请求"}, status_code=403)
        token = os.environ.get(config["token_env"])
        if token and (request.url.path.startswith("/api/") or request.url.path in {"/docs", "/openapi.json", "/redoc"}) and request.url.path != "/api/v1/session":
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ") or request.cookies.get("voice_session", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "需要平台访问令牌"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; worker-src blob:; frame-ancestors 'none'"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.post("/api/v1/session")
    async def session(request: Request):
        body = await request.json()
        expected = os.environ.get(config["token_env"])
        if expected and not secrets.compare_digest(str(body.get("token", "")), expected):
            return JSONResponse({"detail": "令牌错误"}, status_code=401)
        response = JSONResponse({"authenticated": True})
        if expected:
            response.set_cookie("voice_session", expected, httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return response

    @app.get("/api/v1/health")
    def health():
        return dict(status="ok", version=__version__, process_id=os.getpid(),worker_alive=bool(platform.worker and platform.worker.is_alive()),
                    longform_workers_alive=all(t.is_alive() for t in platform.longform.threads),
                    reference_worker_alive=bool(platform.references.thread and platform.references.thread.is_alive()),
                    active_engine=platform.active_engine, loaded_at=platform.loaded_at,
                    queued=sum(j["status"] == "queued" for j in platform.store.list("jobs")))

    @app.get('/api/v1/longform/books')
    def books(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
        return platform.longform.db.books(limit,offset)

    @app.post('/api/v1/longform/books',status_code=202)
    async def import_book(file:UploadFile=File(...),title:str=Form('',max_length=100),encoding:str=Form('auto'),voice_id:str=Form(''),project_id:str=Form(''),style:str=Form('',max_length=1000),clone_mode:str=Form('reference')):
        request=GenerationInput(text='长文配音配置',voice_id=voice_id or None,project_id=project_id or None,style=style,clone_mode=clone_mode,max_retries=0)
        return await platform.longform.upload(file,title,encoding,request)

    @app.get('/api/v1/longform/books/{identity}')
    def book(identity:str):return platform.longform.book(identity)

    @app.get('/api/v1/longform/books/{identity}/configuration')
    def book_configuration(identity:str):
        b=platform.longform.db.book(identity);return dict(snapshot=b['snapshot'],config=b['config'],config_sha256=b.get('config_sha256'))

    @app.get('/api/v1/longform/books/{identity}/source')
    def book_source(identity:str):
        b=platform.longform.db.book(identity);return FileResponse(platform.data/b['original_path'],filename=b['original_name'])

    @app.post('/api/v1/longform/books/{identity}/retry-import',status_code=202)
    def retry_book_import(identity:str,request:LongformImportRetry):return platform.longform.retry_import(identity,request.encoding)

    @app.get('/api/v1/longform/books/{identity}/chapters')
    def book_chapters(identity:str,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):return platform.longform.db.chapters(identity,limit,offset)

    @app.get('/api/v1/longform/books/{identity}/chapters/{chapter}')
    def book_chapter(identity:str,chapter:int):return platform.longform.db.chapter(identity,chapter)

    @app.get('/api/v1/longform/books/{identity}/chapters/{chapter}/segments')
    def book_segments(identity:str,chapter:int,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),status:str|None=Query(None,pattern='^(pending|running|succeeded|failed)$')):
        return platform.longform.segments(identity,chapter,limit,offset,status)

    @app.get('/api/v1/longform/books/{identity}/chapters/{chapter}/next-audio')
    def book_next_audio(identity:str,chapter:int,after:int=Query(0,ge=0)):
        return platform.longform.next_audio(identity,chapter,after)

    @app.get('/api/v1/longform/books/{identity}/segments/{number}/audio')
    def book_segment_audio(identity:str,number:int):return FileResponse(platform.longform.audio(identity,number),media_type='audio/wav')

    @app.get('/api/v1/longform/books/{identity}/segments/{number}/attempts')
    def book_segment_attempts(identity:str,number:int,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
        platform.longform.db.segment(identity,number);return platform.longform.db.rows('lf_attempts','book_id=? AND segment_no=?',[identity,number],order='attempt DESC',limit=limit,offset=offset)

    @app.post('/api/v1/longform/books/{identity}/resume')
    def resume_book(identity:str,request:LongformAction):return platform.longform.resume(identity,request.chapter_no)

    @app.post('/api/v1/longform/books/{identity}/pause')
    def pause_book(identity:str):return platform.longform.pause(identity)

    @app.post('/api/v1/longform/books/{identity}/retry-failed')
    def retry_book_failed(identity:str,request:LongformAction):return platform.longform.retry(identity,chapter=request.chapter_no)

    @app.post('/api/v1/longform/books/{identity}/segments/{number}/retry')
    def retry_book_segment(identity:str,number:int):return platform.longform.retry(identity,number=number)

    @app.post('/api/v1/longform/books/{identity}/segments/{number}/regenerate')
    def regenerate_book_segment(identity:str,number:int):return platform.longform.regenerate(identity,number)

    @app.post('/api/v1/longform/books/{identity}/chapters/{chapter}/review')
    def review_book_chapter(identity:str,chapter:int,request:ReviewInput):return platform.longform.review(identity,chapter,request)

    @app.post('/api/v1/longform/books/{identity}/exports',status_code=202)
    def export_book(identity:str,request:LongformExportInput):return platform.longform.exporter.submit(identity,request)

    @app.get('/api/v1/longform/books/{identity}/exports')
    def book_exports(identity:str,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):return platform.longform.db.exports(identity,limit,offset)

    @app.get('/api/v1/longform/exports/{identity}')
    def book_export_status(identity:str):return platform.longform.db.export(identity)

    @app.post('/api/v1/longform/exports/{identity}/cancel')
    def book_export_cancel(identity:str):return platform.longform.exporter.cancel(identity)

    @app.get('/api/v1/longform/exports/{identity}/download')
    def book_export_download(identity:str):
        item=platform.longform.db.export(identity)
        if item['state']!='succeeded':raise ValueError('导出尚未完成')
        return FileResponse(platform.data/item['path'],filename=('DRAFT_' if item['request']['draft'] else '')+'longform-'+item['id']+'.zip',media_type='application/zip')

    @app.get('/api/v1/assets/kinds')
    def asset_kinds():return KINDS

    @app.get('/api/v1/assets')
    def asset_page(kind:str,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),deleted:bool=False,book_id:str|None=None):
        return platform.assets.page(kind,limit,offset,deleted,book_id)

    @app.post('/api/v1/assets/delete-preview')
    def delete_preview(request:AssetBatch):return platform.assets.preview(request.items,request.cascade)

    @app.post('/api/v1/assets/delete')
    def delete_assets(request:AssetBatch):return platform.assets.delete(request.items,request.cascade)

    @app.post('/api/v1/assets/restore')
    def restore_assets(request:AssetBatch):return platform.assets.restore(request.items)

    @app.post('/api/v1/assets/restore-batch/{identity}')
    def restore_asset_batch(identity:str):return platform.assets.restore_batch(identity)

    @app.post('/api/v1/results/review-batch')
    def review_result_batch(request:ReviewBatch):return platform.review_batch(request)

    @app.get("/api/v1/models")
    def models():
        return platform.models()

    @app.post("/api/v1/models/unload")
    def unload():
        platform.unload()
        return {"released": True}

    @app.get("/api/v1/settings")
    def settings():
        return dict(host=config["host"], port=config["port"], device=config["device"], model_dir=config["model_dir"],
                    data_dir=config["data_dir"], idle_unload_seconds=config["idle_unload_seconds"], concurrency=1,
                    segment_chars=config["segment_chars"], ffmpeg_available=bool(shutil.which(config["ffmpeg"])),
                    segment_pause_ms=config["segment_pause_ms"], max_pending_jobs=config["max_pending_jobs"],
                    task_archive_after_days=config.get('task_archive_after_days',7),
                    export_adapters=list(config["export_adapters"]), runtime=platform.runtime,
                    authentication=bool(os.environ.get(config["token_env"])))

    @app.put("/api/v1/settings")
    def update_settings(request: SettingsInput):
        return platform.update_settings(request)

    @app.post("/api/v1/maintenance/backup")
    def backup():
        return platform.backup()

    @app.get("/api/v1/logs")
    def logs():
        path = Path(config["log_dir"]) / "platform.log"
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 24000))
            return {"text": stream.read().decode("utf-8", errors="replace")}

    @app.get("/api/v1/projects")
    def projects():
        return platform.store.list("projects")

    @app.post("/api/v1/projects", status_code=201)
    def create_project(request: ProjectInput):
        return platform.create_project(request)

    @app.get("/api/v1/voices")
    def voices(project_id: str | None = None):
        values = platform.store.list("voices")
        return [v for v in values if not project_id or not v["project_id"] or v["project_id"] == project_id]

    @app.get("/api/v1/voices/{identity}")
    def voice(identity: str):
        return platform.store.get("voices", identity)

    @app.get("/api/v1/voices/{identity}/versions")
    def versions(identity: str):
        platform.store.get("voices", identity)
        return [v for v in platform.store.list("voice_versions") if v["voice_id"] == identity]

    @app.post("/api/v1/voices", status_code=201)
    def create_voice(request: VoiceInput):
        return platform.create_voice(request)

    @app.put("/api/v1/voices/{identity}")
    def update_voice(identity: str, request: VoiceInput):
        return platform.create_voice(request, identity)

    @app.post("/api/v1/references", status_code=201)
    async def reference(file: UploadFile = File(...), source: str = Form(...), authorization: str = Form(...), rights_confirmed: bool = Form(False)):
        content = await file.read(config["max_upload_mb"] * 1024*1024 + 1)
        return await asyncio.to_thread(platform.upload_reference, file.filename or "reference.wav", content, source, authorization, rights_confirmed)

    @app.get("/api/v1/references")
    def references():
        return [r for r in platform.store.list('references') if r.get('saved',True)]

    @app.post('/api/v1/recordings',status_code=202)
    async def recording(file:UploadFile=File(...),source:str=Form(...),authorization:str=Form(...),rights_confirmed:bool=Form(False),smart_reference:bool=Form(False)):
        content=await file.read(config['max_upload_mb']*1024**2+1)
        return await asyncio.to_thread(platform.references.upload,file.filename or 'recording.wav',content,source,authorization,rights_confirmed,smart_reference)

    @app.post('/api/v1/recordings/from-result',status_code=202)
    def result_recording(request:ResultRecordingInput):
        result=platform.store.get('results',request.result_id);path=platform.data/result['path']
        if sha256(path)!=result['sha256']:raise ValueError('生成结果哈希不匹配')
        return platform.references.upload(result['title']+'.wav',path.read_bytes(),'本平台生成的虚构声音；结果 '+result['id'],'本机生成样音，保存为待审核参考；未声称为真人身份',True,metadata=dict(generated_result_id=result['id'],source_label='设计声音样音'))

    @app.get('/api/v1/audio-processing/capabilities')
    def processing_capabilities():return platform.restoration.capabilities()

    @app.post('/api/v1/audio-processing',status_code=202)
    def processing(request:ProcessingInput):return platform.restoration.submit(request)

    @app.get('/api/v1/audio-processing')
    def processing_list():return platform.store.list('audio_processing')

    @app.get('/api/v1/audio-processing/{identity}')
    def processing_detail(identity:str):return platform.store.get('audio_processing',identity)

    @app.post('/api/v1/audio-processing/{identity}/cancel')
    def processing_cancel(identity:str):return platform.restoration.cancel(identity)

    @app.get('/api/v1/audio-processing/{identity}/before')
    def processing_before(identity:str):
        item=platform.store.get('audio_processing',identity)
        if not item.get('before_path'):raise ValueError('任务尚未解码原件，请稍候')
        return FileResponse(platform.data/item['before_path'],media_type='audio/wav')

    @app.get('/api/v1/audio-processing/{identity}/outputs/{output_id}')
    def processing_audio(identity:str,output_id:str):
        item=platform.store.get('audio_processing',identity);output=next((o for o in item['outputs'] if o['id']==output_id),None)
        if not output:raise KeyError('处理输出不存在')
        return FileResponse(platform.data/output['path'],media_type='audio/wav')

    @app.post('/api/v1/audio-processing/{identity}/analyze-output',status_code=202)
    def processing_analyze(identity:str,request:OutputRecordingInput):return platform.restoration.import_output(identity,request.output_id)

    @app.post('/api/v1/reference-voices',status_code=201)
    def reference_voice(request:ReferenceVoiceInput):return platform.restoration.create_reference_voice(request)

    @app.get('/api/v1/recordings')
    def recordings():return platform.store.list('recordings')

    @app.get('/api/v1/recordings/{identity}')
    def recording_detail(identity:str):return platform.references.detail(identity)

    @app.get('/api/v1/recordings/{identity}/original')
    def original_recording(identity:str):
        r=platform.store.get('recordings',identity)
        return FileResponse(platform.data/r['original_path'])

    @app.post('/api/v1/recordings/{identity}/save')
    def save_clips(identity:str,request:SaveClipsInput):return platform.references.save(identity,request.reference_ids)

    @app.post('/api/v1/recordings/{identity}/retry',status_code=202)
    def retry_recording(identity:str):return platform.references.retry(identity)

    @app.post('/api/v1/recordings/{identity}/cancel')
    def cancel_recording(identity:str):return platform.references.cancel(identity)

    @app.put('/api/v1/references/{identity}/transcript')
    def transcript(identity:str,request:TranscriptInput):return platform.references.transcript(identity,request)

    @app.post('/api/v1/reference-comparisons',status_code=202)
    def compare_references(request:CompareReferencesInput):return platform.references.compare(request)

    @app.get('/api/v1/reference-comparisons')
    def reference_comparisons():return platform.store.list('reference_comparisons')

    @app.get('/api/v1/reference-comparisons/{identity}')
    def reference_comparison(identity:str):return platform.store.get('reference_comparisons',identity)

    @app.post('/api/v1/reference-comparisons/{identity}/apply')
    def apply_reference(identity:str):return platform.references.apply_recommendation(identity)

    @app.get("/api/v1/references/{identity}/audio")
    def reference_audio(identity: str):
        item = platform.store.get("references", identity)
        return FileResponse(platform.data / item["path"], media_type="audio/wav")

    @app.post("/api/v1/jobs", status_code=202)
    def create_job(request: GenerationInput):
        return platform.submit([request])[0]

    @app.post("/api/v1/batches", status_code=202)
    def batch(request: BatchInput):
        jobs = platform.submit(request.items, batch=True)
        return dict(batch_id=jobs[0]["batch_id"], jobs=jobs)

    @app.get("/api/v1/jobs")
    def jobs(project_id: str | None = None, archived: bool = False):
        platform.archive_due()
        return platform.store.jobs(archived=archived,project_id=project_id)['items']

    @app.get('/api/v1/jobs/page')
    def job_page(archived:bool=False, project_id:str|None=None, status:str|None=None, limit:int=Query(default=50,ge=1,le=200),offset:int=Query(default=0,ge=0)):
        platform.archive_due()
        return dict(platform.store.jobs(archived,project_id,status,limit,offset),limit=limit,offset=offset,archived=archived,task_archive_after_days=config.get('task_archive_after_days',7))

    @app.post('/api/v1/jobs/archive')
    def archive_jobs(request:ArchiveJobsInput):
        return platform.archive_jobs(request.job_ids)

    @app.post('/api/v1/jobs/restore')
    def restore_jobs(request:ArchiveJobsInput):
        return platform.archive_jobs(request.job_ids,restore=True)

    @app.get("/api/v1/jobs/{identity}")
    def job(identity: str):
        return platform.store.get("jobs", identity)

    @app.post("/api/v1/jobs/{identity}/cancel")
    def cancel(identity: str):
        return platform.cancel(identity)

    @app.post("/api/v1/jobs/{identity}/retry", status_code=202)
    def retry(identity: str):
        return platform.retry(identity)

    @app.get("/api/v1/jobs/{identity}/events")
    def events(identity: str):
        platform.store.get("jobs", identity)
        return [e for e in reversed(platform.store.list("events")) if e["job_id"] == identity]

    @app.get("/api/v1/jobs/{identity}/stream")
    async def stream(identity: str, request: Request):
        platform.store.get("jobs", identity)
        async def iterator():
            seen = set()
            while not await request.is_disconnected():
                items = [e for e in reversed(platform.store.list("events")) if e["job_id"] == identity and e["id"] not in seen]
                for item in items:
                    seen.add(item["id"])
                    yield f"id: {item['id']}\nevent: {item['event']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                if platform.store.get("jobs", identity)["status"] in TERMINAL:
                    yield "event: end\ndata: {}\n\n"
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(iterator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/events/{identity}/audio")
    def chunk(identity: str):
        item = platform.store.get("events", identity)
        if item["event"] != "audio_chunk":
            raise ValueError("此事件没有音频片段")
        return FileResponse(platform.data / item["path"], media_type="audio/wav")

    @app.get("/api/v1/results")
    def results(project_id: str | None = None):
        return [r for r in platform.store.list("results") if not project_id or r["project_id"] == project_id]

    @app.get("/api/v1/results/{identity}")
    def result(identity: str):
        return platform.store.get("results", identity)

    @app.get("/api/v1/results/{identity}/audio")
    def audio(identity: str):
        item = platform.store.get("results", identity)
        return FileResponse(platform.data / item["path"], media_type="audio/wav", filename=f"{identity}.wav")

    @app.get("/api/v1/results/{identity}/subtitles")
    def subtitles(identity: str):
        item = platform.store.get("results", identity)
        return FileResponse((platform.data / item["path"]).parent / "segments.srt", filename=f"{identity}.srt")

    @app.put("/api/v1/results/{identity}/review")
    def review(identity: str, request: ReviewInput):
        return platform.review(identity, request)

    @app.post("/api/v1/exports", status_code=201)
    def export(request: ExportInput):
        return platform.export(request)

    @app.get("/api/v1/exports")
    def exports():
        return platform.store.list("exports")

    @app.get("/api/v1/exports/{identity}/download")
    def download(identity: str):
        item = platform.store.get("exports", identity)
        return FileResponse(platform.data / item["path"], media_type="application/zip", filename=f"voice-export-{identity}.zip")

    @app.post("/api/v1/maintenance/stop", status_code=202)
    def stop():
        # Launcher-owned servers only. A separate thread lets the HTTP response complete.
        app.state.stop_requested = True
        return {"stop_requested": True}

    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
    return app
