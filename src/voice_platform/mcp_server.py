from mcp.server.fastmcp import FastMCP
from .client import Client
from .cli import copy_export,download_book_export
from functools import lru_cache
from pathlib import Path

mcp = FastMCP("voice-foundry", instructions="独立本地语音生产平台；所有项目共用此服务。先查模型能力和音色。情绪、语速、风格为近似控制。生成结果默认待审核，工具不能代替用户试听审核；正式导出仅允许人工批准结果。")

@lru_cache(maxsize=1)
def _client():
    return Client()

def api():
    client = _client()
    client.ensure_running()
    return client

@mcp.tool()
def voice_models() -> list:
    """查询实际模型版本、语言、克隆/设计/流式能力及近似控制边界。"""
    return api().request("GET", "/models")

@mcp.tool()
def voice_library(project_id: str | None = None) -> list:
    """查询全局共享和指定项目专属的音色；使用稳定 Voice ID 复用已确认参考。"""
    return api().request("GET", "/voices", params={"project_id": project_id} if project_id else {})

@mcp.tool()
def voice_projects() -> list:
    """查询独立配音项目，不读取或修改任何游戏工程。"""
    return api().request("GET", "/projects")

@mcp.tool()
def voice_create_project(name: str, kind: str = "通用", description: str = "") -> dict:
    """建立独立任务与资产分组，可用于游戏、影视、广告或其他内容。"""
    return api().request("POST", "/projects", json=dict(name=name, kind=kind, description=description))

@mcp.tool()
def voice_generate(text: str, title: str = "语音配音", voice_id: str | None = None, project_id: str | None = None,
                   style: str = "", seed: int | None = None, candidates: int = 1, language: str = "auto", streaming: bool = False, engine: str | None = None, engine_options: dict | None = None,reference_id: str | None = None,clone_mode: str = 'reference') -> dict:
    """异步生成文字配音或设计声音。style 例如“沉稳成年男性，温和叙述”，效果为近似引导。返回任务 ID，随后查询进度。"""
    return api().request("POST", "/jobs", json=dict(text=text, title=title, voice_id=voice_id, project_id=project_id,
                     style=style, seed=seed, candidates=candidates, language=language, streaming=streaming,engine=engine,engine_options=engine_options or {},reference_id=reference_id,clone_mode=clone_mode))

@mcp.tool()
def voice_batch(items: list[dict]) -> dict:
    """批量剧本配音，每项包含 text，可分别指定 title、voice_id、project_id、style、seed、candidates。最多 200 项。"""
    return api().request("POST", "/batches", json={"items": items})

@mcp.tool()
def voice_job(job_id: str) -> dict:
    """查询任务状态、进度、失败原因与结果 ID。任务独立于当前工作目录。"""
    return api().request("GET", f"/jobs/{job_id}")

@mcp.tool()
def voice_result(result_id: str) -> dict:
    """读取结果追踪元数据与审核状态，audio_url 可打开试听原始 WAV。"""
    client = api()
    return dict(client.request("GET", f"/results/{result_id}"), audio_url=f"{client.url}/api/v1/results/{result_id}/audio")

@mcp.tool()
def voice_cancel(job_id: str) -> dict:
    """取消排队任务；运行中任务在下个生成片段/分段边界停止。"""
    return api().request("POST", f"/jobs/{job_id}/cancel")

@mcp.tool()
def voice_retry(job_id: str) -> dict:
    """使用冻结的音色版本与种子重试失败任务，保留原任务和已有音频。"""
    return api().request("POST", f"/jobs/{job_id}/retry")

@mcp.tool()
def voice_archive_jobs(job_ids:list[str],restore:bool=False)->dict:
    """归档已结束任务或恢复归档。原始音频、审核、导出和生成记录保留；不能归档排队及运行中的任务。"""
    return api().request('POST','/jobs/'+('restore' if restore else 'archive'),json={'job_ids':job_ids})

@mcp.tool()
def voice_save(name: str, description: str = "", style: str = "", seed: int = 42, reference_id: str | None = None,
               project_id: str | None = None, tags: list[str] | None = None,engine: str | None = None,engine_options: dict | None = None,reference_ids:list[str]|None=None,reference_scenarios:dict|None=None) -> dict:
    """保存可跨项目复用的草稿音色。传 project_id 则为项目专属。正式启用与参考确认需要用户在 WebUI 试听确认。"""
    return api().request("POST", "/voices", json=dict(name=name, description=description, style=style, seed=seed,
             reference_id=reference_id, project_id=project_id, tags=tags or [],engine=engine,engine_options=engine_options or {},reference_ids=reference_ids or [],reference_scenarios=reference_scenarios or {}))

@mcp.tool()
def voice_upload_recording(path:str,source:str,authorization:str,rights_confirmed:bool=False,smart_reference:bool=True)->dict:
    """将指定本机录音上传到本机平台智能整理：自动分离、清理、切分、转写并推荐参考。原件保留；异步返回录音 ID。smart_reference=false 则仅分析，不做分离。"""
    file=Path(path)
    if not file.is_absolute():raise ValueError('请使用用户明确指定的绝对录音路径')
    client=api()
    if file.stat().st_size>client.config['max_upload_mb']*1024**2:raise ValueError('录音超过上传限制')
    with file.open('rb') as stream:
        return client.request('POST','/recordings',files={'file':(file.name,stream)},data=dict(source=source,authorization=authorization,rights_confirmed=str(rights_confirmed).lower(),smart_reference=str(smart_reference).lower()))

@mcp.tool()
def voice_process_recording(recording_id:str,operations:list[str]|None=None)->dict:
    """独立处理已有录音。operations 可用 remove_music / separate / denoise，默认依次去音乐、双人分离、降噪。另存输出，原件不变；处理效果需试听。"""
    return api().request('POST','/audio-processing',json=dict(recording_id=recording_id,operations=operations or ['remove_music','separate','denoise'],analyze_outputs=True))

@mcp.tool()
def voice_audio_processing(processing_id:str)->dict:
    """查询处理进度、独立输出与前后试听地址。两路分离为匿名输出，不是身份识别。"""
    client=api();item=client.request('GET','/audio-processing/'+processing_id);item.pop('source_snapshot',None)
    item['before_audio_url']=client.url+'/api/v1/audio-processing/'+processing_id+'/before'
    for output in item['outputs']:output['audio_url']=client.url+'/api/v1/audio-processing/'+processing_id+'/outputs/'+output['id']
    return item

@mcp.tool()
def voice_create_from_reference(reference_id:str,name:str)->dict:
    """将用户选中的参考片段保存为可复用人物草稿。保留原件、处理链、转写和来源；不自动试听确认或批准。"""
    return api().request('POST','/reference-voices',json=dict(reference_id=reference_id,name=name))

@mcp.tool()
def voice_recording(recording_id:str)->dict:
    """查询人声切段、近似说话人、音乐噪声提示和转写；未知或低置信度不能当作干净录音。"""
    item=api().request('GET','/recordings/'+recording_id)
    for candidate in item.get('candidates',[]):candidate.pop('embedding',None)
    if 'summary' in item:item['summary'].pop('classifier_windows',None);item['summary'].pop('speaker_windows',None)
    return item

@mcp.tool()
def voice_save_reference_clips(recording_id:str,reference_ids:list[str])->list:
    """保存用户选中的多个独立参考片段；不拼接，不自动批准。"""
    result=api().request('POST','/recordings/'+recording_id+'/save',json={'reference_ids':reference_ids})
    for item in result:item.pop('embedding',None)
    return result

@mcp.tool()
def voice_compare_references(voice_id:str,reference_ids:list[str],text:str='夜色渐深，城市终于安静下来。故事，就从这里开始。',clone_mode:str='reference')->dict:
    """对每个已保存参考分别用同文本、两个种子克隆，异步比较声线/一致性/ASR。自动建议不代替试听。"""
    return api().request('POST','/reference-comparisons',json=dict(voice_id=voice_id,reference_ids=reference_ids,text=text,clone_mode=clone_mode))

@mcp.tool()
def voice_reference_comparison(comparison_id:str)->dict:
    """查询参考克隆对比排名与试听结果。应用主参考需用户在界面选择，保留其他场景参考。"""
    item=api().request('GET','/reference-comparisons/'+comparison_id);item.pop('reference_snapshots',None);return item

@mcp.tool()
def voice_export(result_ids: list[str], destination: str, adapter: str = "standard", format: str = "wav", draft: bool = False) -> dict:
    """将选定结果导出到用户明确指定的本机目录。正式导出必须已人工批准；草稿需显式 draft=true。创建唯一子目录，不覆盖已有文件。"""
    client = api()
    package = client.request("POST", "/exports", json=dict(result_ids=result_ids, adapter=adapter, format=format, draft=draft))
    return copy_export(client, package, destination)

@mcp.tool()
def voice_release_models() -> dict:
    """空闲时释放本服务的模型显存，不影响其他应用。"""
    return _client().request("POST", "/models/unload")

@mcp.tool()
def voice_stop_service() -> dict:
    """停止语音服务及其推理进程，等待退出；保留已保存资产，不自动重启。"""
    return _client().stop()

@mcp.tool()
def voice_import_book(path:str,title:str='',encoding:str='auto',voice_id:str='',project_id:str='')->dict:
    """整本导入本机 TXT/Markdown，流式上传；支持 GB2312/GBK/GB18030、UTF-8/UTF-16。后台自动章节/段落拆分，默认暂停，保存原件。"""
    file=Path(path).resolve()
    with file.open('rb') as stream:return api().request('POST','/longform/books',files={'file':(file.name,stream,'text/plain')},data=dict(title=title,encoding=encoding,voice_id=voice_id,project_id=project_id))

@mcp.tool()
def voice_books(limit:int=20,offset:int=0)->dict:
    """分页查询长篇作品、导入与生成进度，不读取整本正文。"""
    return api().request('GET','/longform/books',params=dict(limit=limit,offset=offset))

@mcp.tool()
def voice_book(book_id:str,chapters:bool=False,limit:int=50,offset:int=0)->dict:
    """查询长文状态，或分页查询章节及审核状态。"""
    return api().request('GET','/longform/books/'+book_id+('/chapters' if chapters else ''),params=dict(limit=limit,offset=offset) if chapters else {})

@mcp.tool()
def voice_book_segments(book_id:str,chapter_no:int,limit:int=50,offset:int=0)->dict:
    """分页查看本章原文分段、生成/失败状态与独立音频。"""
    return api().request('GET',f'/longform/books/{book_id}/chapters/{chapter_no}/segments',params=dict(limit=limit,offset=offset))

@mcp.tool()
def voice_book_action(book_id:str,action:str,chapter_no:int|None=None)->dict:
    """resume 断点续作、pause 暂停、retry-failed 重排失败段；成功段不重做。可限定章节；重试后需 resume。"""
    if action not in {'resume','pause','retry-failed'}:raise ValueError('action 仅支持 resume/pause/retry-failed')
    return api().request('POST',f'/longform/books/{book_id}/{action}',json=dict(chapter_no=chapter_no) if action!='pause' else {})

@mcp.tool()
def voice_book_export(book_id:str,chapter_no:int|None=None,mode:str='chapters',format:str='wav',draft:bool=False)->dict:
    """异步按章节或整本导出。正式导出只允许用户已试听审核的当前章节版本；草稿必须明确 draft=true，不能由工具代替审核。"""
    return api().request('POST',f'/longform/books/{book_id}/exports',json=dict(chapter_no=chapter_no,mode=mode,format=format,draft=draft))

@mcp.tool()
def voice_book_export_status(export_id:str)->dict:
    """查询后台长文导出及下载地址；大文件按块处理，不加载全书音频。"""
    client=api();item=client.request('GET','/longform/exports/'+export_id)
    if item['state']=='succeeded':item['download_url']=f'{client.url}/api/v1/longform/exports/{export_id}/download'
    return item

@mcp.tool()
def voice_book_download(export_id:str,destination:str)->dict:
    """将已完成的长文导出分块下载到用户指定目录的唯一子目录，校验 SHA256，保留 ZIP64 压缩包，不覆盖已有文件。"""
    return download_book_export(api(),export_id,destination)

@mcp.tool()
def voice_assets(kind:str,deleted:bool=False,limit:int=50,offset:int=0,book_id:str|None=None)->dict:
    """分页管理项目、音色、参考录音/片段、任务、试听、导出、长文作品/章节/分段；deleted=true 查询可恢复回收站。"""
    return api().request('GET','/assets',params={k:v for k,v in dict(kind=kind,deleted=deleted,limit=limit,offset=offset,book_id=book_id).items() if v is not None})

@mcp.tool()
def voice_delete_assets(items:list[dict],cascade:bool=True,preview_only:bool=True)->dict:
    """仅在用户明确要求删除指定资产时使用。默认预览引用和影响；确认对象后 preview_only=false 可恢复地移入回收站，原文件不物理删除。items 每项 kind/id，最多200项。"""
    return api().request('POST','/assets/'+('delete-preview' if preview_only else 'delete'),json=dict(items=items,cascade=cascade))

@mcp.tool()
def voice_restore_assets(items:list[dict]|None=None,batch_id:str|None=None)->dict:
    """恢复指定回收站资产，或用 batch_id 恢复同次删除的关联记录。不自动批准音频。"""
    if batch_id:return api().request('POST','/assets/restore-batch/'+batch_id)
    return api().request('POST','/assets/restore',json=dict(items=items or []))

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
