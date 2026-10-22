import argparse
import hashlib
import json
import shutil
import sys
import zipfile
import webbrowser
from pathlib import Path
from .client import Client

def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))

def copy_export(client, package, destination):
    dest = Path(destination).resolve() / f"voice-export-{package['id']}"
    dest.mkdir(parents=True, exist_ok=False)
    archive = dest / "package.zip"
    response = client.http.get(f"/api/v1/exports/{package['id']}/download")
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != package["sha256"]:
        raise ValueError("下载包哈希不匹配")
    archive.write_bytes(response.content)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            path = (dest / item.filename).resolve()
            if not path.is_relative_to(dest) or path == dest:
                raise ValueError("导出包内含非法路径")
        source.extractall(dest)
    return dict(package, destination=str(dest))

def download_book_export(client,identity,destination):
    item=client.request('GET','/longform/exports/'+identity)
    if item['state']!='succeeded':raise ValueError('导出尚未完成')
    folder=Path(destination).resolve()/('voice-book-export-'+identity);folder.mkdir(parents=True,exist_ok=False)
    partial=folder/'package.partial';digest=hashlib.sha256()
    with client.http.stream('GET',f'/api/v1/longform/exports/{identity}/download') as response:
        response.raise_for_status()
        with partial.open('xb') as out:
            for block in response.iter_bytes(1024*1024):out.write(block);digest.update(block)
    if digest.hexdigest()!=item['sha256']:raise ValueError('下载校验失败，部分文件保留')
    target=folder/(('DRAFT_' if item['request']['draft'] else '')+'book-export.zip');partial.replace(target)
    return dict(id=identity,path=str(target),sha256=item['sha256'],bytes=target.stat().st_size)

def parser():
    p = argparse.ArgumentParser(description="声场：全局本地语音平台，所有目录使用同一服务与模型")
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("start", "ui", "stop", "health", "models", "unload", "settings", "backup", "voices", "projects", "jobs", "results", "exports", "recordings"):
        commands.add_parser(name)
    commands.choices['jobs'].add_argument('--archived',action='store_true',help='查看已归档任务')
    generate = commands.add_parser("generate")
    text = generate.add_mutually_exclusive_group(required=True)
    text.add_argument("--text")
    text.add_argument("--text-file")
    generate.add_argument("--title", default="CLI 配音")
    generate.add_argument("--voice-id")
    generate.add_argument('--reference-id')
    generate.add_argument('--clone-mode',choices=['reference','hifi'],default='reference')
    generate.add_argument("--project-id")
    generate.add_argument("--engine")
    generate.add_argument("--style", default="")
    generate.add_argument("--language", default="auto")
    generate.add_argument("--seed", type=int)
    generate.add_argument("--candidates", type=int, default=1)
    generate.add_argument("--streaming", action="store_true")
    generate.add_argument("--engine-options", default="{}", help="模型能力声明中的参数，JSON 对象")
    generate.add_argument("--wait", action="store_true")
    book_import=commands.add_parser('import-book');book_import.add_argument('file');book_import.add_argument('--title',default='');book_import.add_argument('--encoding',default='auto',choices=['auto','utf-8-sig','utf-16','utf-16-le','utf-16-be','gb2312','gbk','gb18030']);book_import.add_argument('--voice-id',default='');book_import.add_argument('--project-id',default='');book_import.add_argument('--style',default='')
    books=commands.add_parser('books');books.add_argument('--limit',type=int,default=20);books.add_argument('--offset',type=int,default=0)
    for name in ['book','book-resume','book-pause','book-retry-failed']:
        c=commands.add_parser(name);c.add_argument('id');c.add_argument('--chapter',type=int)
        if name=='book':c.add_argument('--chapters',action='store_true');c.add_argument('--limit',type=int,default=50);c.add_argument('--offset',type=int,default=0)
    segments=commands.add_parser('book-segments');segments.add_argument('id');segments.add_argument('chapter',type=int);segments.add_argument('--limit',type=int,default=50);segments.add_argument('--offset',type=int,default=0)
    export_book=commands.add_parser('book-export');export_book.add_argument('id');export_book.add_argument('--chapter',type=int);export_book.add_argument('--mode',choices=['chapters','book'],default='chapters');export_book.add_argument('--format',choices=['wav','mp3','flac','ogg'],default='wav');export_book.add_argument('--draft',action='store_true')
    commands.add_parser('book-export-status').add_argument('id')
    download=commands.add_parser('book-download');download.add_argument('id');download.add_argument('--dest',required=True)
    assets=commands.add_parser('assets');assets.add_argument('--kind',required=True);assets.add_argument('--deleted',action='store_true');assets.add_argument('--book-id');assets.add_argument('--limit',type=int,default=50);assets.add_argument('--offset',type=int,default=0)
    for name in ['delete-assets','restore-assets']:
        c=commands.add_parser(name);c.add_argument('--kind',required=True);c.add_argument('--ids',nargs='+',required=True)
        if name=='delete-assets':c.add_argument('--apply',action='store_true',help='默认预览；显式应用后移入可恢复回收站');c.add_argument('--no-cascade',action='store_true')
    commands.add_parser('restore-asset-batch').add_argument('id')
    batch = commands.add_parser("batch")
    batch.add_argument("file", help="UTF-8 JSON，包含 items 列表；每条可指定自己的 voice_id 和 project_id")
    for name in ("job", "wait", "cancel", "retry", "recording", "archive-job", "restore-job"):
        command = commands.add_parser(name)
        command.add_argument("id")
    for name in ("create-voice", "update-voice", "create-project"):
        command = commands.add_parser(name)
        command.add_argument("file", help="UTF-8 JSON")
        if name == "update-voice":
            command.add_argument("id")
    reference = commands.add_parser("upload-reference")
    reference.add_argument("file")
    reference.add_argument("--source", required=True)
    reference.add_argument("--authorization", required=True)
    reference.add_argument("--rights-confirmed", action="store_true")
    reference.add_argument('--direct',action='store_true',help='旧版短音频直传；默认自动预处理并返回录音任务')
    reference.add_argument('--analyze-only',action='store_true',help='仅切分转写，不进入智能分离和清理流程')
    process=commands.add_parser('process-audio');process.add_argument('recording_id');process.add_argument('--operations',nargs='+',choices=['remove_music','separate','denoise'],default=['remove_music','separate','denoise'])
    processing=commands.add_parser('processing');processing.add_argument('id')
    export = commands.add_parser("export")
    export.add_argument("--ids", nargs="+", required=True)
    export.add_argument("--dest", required=True)
    export.add_argument("--adapter", default="standard")
    export.add_argument("--format", choices=["wav", "mp3", "flac", "ogg"], default="wav")
    export.add_argument("--sample-rate", type=int, default=48000)
    export.add_argument("--channels", type=int, choices=[1,2], default=1)
    export.add_argument("--normalize", action="store_true")
    export.add_argument("--trim-silence", action="store_true")
    export.add_argument("--no-subtitles", action="store_true")
    export.add_argument("--draft", action="store_true")
    export.add_argument("--naming", default="{title}_{candidate}_{id}")
    return p

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        client = Client(auto_start=args.command not in {"health", "stop"})
        command = args.command
        if command in {"start", "ui"}:
            output = dict(client.request("GET", "/health"), webui=client.url)
            if command == "ui":
                output["browser_opened"] = webbrowser.open(client.url)
        elif command in {"health", "settings", "models", "voices", "projects", "jobs", "results", "exports", "recordings"}:
            output = client.request("GET", "/"+command,params={'archived':str(args.archived).lower()} if command=='jobs' else {})
        elif command in {"stop", "backup"}:
            output = client.request("POST", "/maintenance/"+command)
        elif command == "unload":
            output = client.request("POST", "/models/unload")
        elif command == "generate":
            body = {k: v for k, v in vars(args).items() if k not in {"command", "wait", "text_file"} and v is not None}
            if args.text_file:
                body["text"] = Path(args.text_file).read_text(encoding="utf-8-sig")
            body["engine_options"] = json.loads(body["engine_options"])
            output = client.request("POST", "/jobs", json=body)
            if args.wait:
                output = client.wait(output["id"], progress=lambda j: print(f"{j['status']} {j['progress']}%", file=sys.stderr))
        elif command=='import-book':
            with Path(args.file).open('rb') as source:
                output=client.request('POST','/longform/books',files={'file':(Path(args.file).name,source,'text/plain')},data=dict(title=args.title,encoding=args.encoding,voice_id=args.voice_id,project_id=args.project_id,style=args.style))
        elif command=='books':output=client.request('GET','/longform/books',params=dict(limit=args.limit,offset=args.offset))
        elif command=='book':output=client.request('GET','/longform/books/'+args.id+('/chapters' if args.chapters else ''),params=dict(limit=args.limit,offset=args.offset) if args.chapters else {})
        elif command in {'book-resume','book-pause','book-retry-failed'}:
            output=client.request('POST','/longform/books/'+args.id+'/'+command.removeprefix('book-'),json=dict(chapter_no=args.chapter) if command!='book-pause' else {})
        elif command=='book-segments':output=client.request('GET',f'/longform/books/{args.id}/chapters/{args.chapter}/segments',params=dict(limit=args.limit,offset=args.offset))
        elif command=='book-export':output=client.request('POST',f'/longform/books/{args.id}/exports',json=dict(chapter_no=args.chapter,mode=args.mode,format=args.format,draft=args.draft))
        elif command=='book-export-status':output=client.request('GET','/longform/exports/'+args.id)
        elif command=='book-download':output=download_book_export(client,args.id,args.dest)
        elif command=='assets':output=client.request('GET','/assets',params={k:v for k,v in dict(kind=args.kind,deleted=args.deleted,book_id=args.book_id,limit=args.limit,offset=args.offset).items() if v is not None})
        elif command in {'delete-assets','restore-assets'}:
            route='restore' if command=='restore-assets' else 'delete' if args.apply else 'delete-preview'
            output=client.request('POST','/assets/'+route,json=dict(items=[dict(kind=args.kind,id=i) for i in args.ids],cascade=not getattr(args,'no_cascade',False)))
        elif command=='restore-asset-batch':output=client.request('POST','/assets/restore-batch/'+args.id)
        elif command == "batch":
            output = client.request("POST", "/batches", json=json.loads(Path(args.file).read_text(encoding="utf-8-sig")))
        elif command in {"job", "wait", "cancel", "retry"}:
            output = client.wait(args.id) if command == "wait" else client.request("GET" if command == "job" else "POST", f"/jobs/{args.id}" + ("" if command == "job" else "/"+command))
        elif command=='recording':
            output=client.request('GET','/recordings/'+args.id)
        elif command=='processing':
            output=client.request('GET','/audio-processing/'+args.id)
        elif command=='process-audio':
            output=client.request('POST','/audio-processing',json=dict(recording_id=args.recording_id,operations=args.operations,analyze_outputs=True))
        elif command in {'archive-job','restore-job'}:
            output=client.request('POST','/jobs/'+('archive' if command=='archive-job' else 'restore'),json={'job_ids':[args.id]})
        elif command in {"create-voice", "update-voice", "create-project"}:
            route = "/projects" if command == "create-project" else "/voices" + ("/"+args.id if command == "update-voice" else "")
            output = client.request("PUT" if command == "update-voice" else "POST", route, json=json.loads(Path(args.file).read_text(encoding="utf-8-sig")))
        elif command == "upload-reference":
            with open(args.file, "rb") as stream:
                output = client.request("POST", "/references" if args.direct else '/recordings', files={"file": (Path(args.file).name, stream)}, data=dict(source=args.source, authorization=args.authorization, rights_confirmed=str(args.rights_confirmed).lower(),smart_reference=str(not args.analyze_only).lower()))
        elif command == "export":
            body = dict(result_ids=args.ids, adapter=args.adapter, format=args.format, sample_rate=args.sample_rate,
                        channels=args.channels, normalize=args.normalize, trim_silence=args.trim_silence,
                        draft=args.draft, subtitles=not args.no_subtitles, naming=args.naming)
            output = copy_export(client, client.request("POST", "/exports", json=body), args.dest)
        show(output)
        if isinstance(output, dict) and output.get("status") in {"failed", "cancelled"}:
            sys.exit(2)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
