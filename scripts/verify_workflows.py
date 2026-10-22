"""Live service acceptance: real inference, cross-project CLI, exports. No auto-approval."""
import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
import soundfile as sf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from voice_platform.client import Client
from voice_platform.cli import copy_export
from voice_platform.config import ROOT
from voice_platform.schemas import VoiceInput

def main():
    client=Client()
    report=dict(started_at=time.time(),voice_approval='pending',production_assets_approved=0,checks={},jobs=[],exports=[])
    evidence=ROOT/'docs/evidence/workflows.json'
    def save():
        evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def completed(job):
        final=client.wait(job['id'],timeout=900)
        assert final['status']=='succeeded',final
        report['jobs'].append(final)
        for rid in final['results']:
            result=client.request('GET',f'/results/{rid}')
            response=client.http.get(f'/api/v1/results/{rid}/audio')
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest()==result['sha256']
            info=sf.info(io.BytesIO(response.content))
            assert info.frames>100 and info.samplerate==48000 and result['review']=='pending'
        save()
        return final
    ui_jobs=[j for j in client.request('GET','/jobs') if j['title']=='界面验收 · 开场旁白']
    assert ui_jobs,'submit real task through browser first'
    ui=completed(ui_jobs[0])
    assert len(ui['results'])==2
    events=client.request('GET',f'/jobs/{ui["id"]}/events')
    chunks=[e for e in events if e['event']=='audio_chunk']
    assert chunks and chunks[0]['created_at']<ui['finished_at']
    report['checks']['real_ui_candidates_and_incremental_stream']=dict(job_id=ui['id'],chunks=len(chunks),first_audio_event=chunks[0]['created_at'],finished=ui['finished_at'])
    projects=client.request('GET','/projects')
    game=next(p for p in projects if p['name']=='验收样例 · 游戏资源')
    media=next(p for p in projects if p['name']=='验收样例 · 纪录短片')
    voice=next(v for v in client.request('GET','/voices') if v['name']=='样例 · 沉稳旁白')
    source=ROOT/'docs/evidence/stage1/design.wav'
    with source.open('rb') as stream:
        reference=client.request('POST','/references',files={'file':('synthetic-design.wav',stream)},data=dict(
            source='本平台阶段一生成的虚构旁白；无真人参考，来源见 docs/evidence/stage1/verification.json',
            authorization='本次本地平台技术测试生成素材，仅作为隔离验收草稿；不代表真人声音授权或成品审核',rights_confirmed='true'))
    body={key:voice[key] for key in VoiceInput.model_fields if key in voice}
    body.update(reference_id=reference['id'],reference_confirmed=False,status='draft',sample_result_id=ui['results'][0])
    updated=client.request('PUT','/voices/'+voice['id'],json=body)
    assert updated['version']>voice['version']
    report['checks']['frozen_reference_and_version']=dict(voice_id=updated['id'],version=updated['version'],reference_id=reference['id'],sha256=reference['sha256'],human_reference_confirmation=False)
    cli_records=[]
    for directory,project,text in ((ROOT/'examples/game_project',game,'前方有光，旅程现在开始。'),(ROOT/'examples/media_project',media,'清晨的第一缕阳光，照亮这座城市。')):
        directory.mkdir(parents=True,exist_ok=True)
        args=[str(ROOT/'bin/voice.cmd'),'generate','--text',text,'--title',f"跨目录验收 · {project['kind']}",'--voice-id',voice['id'],'--project-id',project['id'],'--seed','42','--wait']
        result=subprocess.run(args,cwd=directory,capture_output=True,timeout=900)
        assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
        job=json.loads(result.stdout.decode('utf-8-sig'))
        final=completed(job)
        package=client.request('POST','/exports',json=dict(result_ids=final['results'],adapter='game_audio' if project is game else 'media_dubbing',draft=True))
        copied=copy_export(client,package,directory/'delivery')
        assert (Path(copied['destination'])/'manifest.json').exists()
        cli_records.append(dict(cwd=str(directory),entry=str(ROOT/'bin/voice.cmd'),job_id=final['id'],voice_id=voice['id'],voice_version=final['voice_snapshot']['version'],destination=copied['destination']))
        report['exports'].append(copied)
        save()
    assert len({r['voice_id'] for r in cli_records})==1
    report['checks']['two_project_types_same_voice_cli']=cli_records
    # Change only future-task segmentation, immediately restore configuration after submission.
    settings=client.request('GET','/settings')
    original={key:settings[key] for key in ('idle_unload_seconds','segment_chars','segment_pause_ms','max_pending_jobs')}
    client.request('PUT','/settings',json=dict(original,segment_chars=40))
    try:
        long_job=client.request('POST','/jobs',json=dict(title='长文分段验收',text='夜色渐深，城市终于安静下来。我们沿着河岸继续前行，看见远处亮起的灯光。每一个故事都值得被认真讲述，而这一段旅程，才刚刚开始。',voice_id=voice['id'],project_id=media['id'],seed=42))
    finally:
        client.request('PUT','/settings',json=original)
    long_job=completed(long_job)
    long_result=client.request('GET','/results/'+long_job['results'][0])
    assert len(long_result['segments'])>=2 and long_job['pipeline']['segment_chars']==40
    report['checks']['long_text_actual_segments']=dict(job_id=long_job['id'],segments=long_result['segments'],pipeline=long_job['pipeline'])
    second_voice=client.request('POST','/voices',json=dict(name='样例 · 明亮讲述',description='测试多角色分配，尚待用户试听',style='年轻女性，清晰明亮，充满活力',seed=84))
    batch=client.request('POST','/batches',json={'items':[
        dict(title='剧本 · 旁白',text='故事从这里开始。',voice_id=voice['id'],project_id=media['id']),
        dict(title='剧本 · 角色',text='准备好了，出发吧！',voice_id=second_voice['id'],project_id=media['id'])]})
    for job in batch['jobs']:
        completed(job)
    report['checks']['real_multi_role_batch']=dict(batch_id=batch['batch_id'],jobs=[j['id'] for j in batch['jobs']])
    rid=long_job['results'][0]
    # Formal export is intentionally denied until a human listens and approves.
    response=client.http.post('/api/v1/exports',json={'result_ids':[rid]})
    assert response.status_code==400
    report['checks']['unreviewed_formal_export_denied']=True
    original_bytes=client.http.get(f'/api/v1/results/{rid}/audio').content
    for format in ('wav','mp3','flac','ogg'):
        package=client.request('POST','/exports',json=dict(result_ids=[rid],draft=True,format=format,normalize=True,sample_rate=24000,channels=2))
        response=client.http.get('/api/v1/exports/'+package['id']+'/download')
        archive=zipfile.ZipFile(io.BytesIO(response.content))
        filename=next(n for n in archive.namelist() if n.endswith('.'+format))
        info=sf.info(io.BytesIO(archive.read(filename)))
        assert info.channels==2 and info.samplerate==24000 and info.duration>0
        report['exports'].append(dict(id=package['id'],format=format,sample_rate=info.samplerate,channels=info.channels,duration=info.duration))
        save()
    package=client.request('POST','/exports',json=dict(result_ids=[rid],draft=True,trim_silence=True,subtitles=False))
    report['exports'].append(dict(id=package['id'],postprocess='trim_silence',subtitles=False))
    assert client.http.get(f'/api/v1/results/{rid}/audio').content==original_bytes
    report['checks']['original_bytes_preserved_after_processing']=True
    # Real MCP generation, independent of CLI and browser.
    async def mcp_generate():
        params=StdioServerParameters(command=sys.executable,args=['-m','voice_platform.mcp_server'],cwd=str(ROOT/'examples/media_project'))
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                result=await session.call_tool('voice_generate',dict(text='这是通过全局工具生成的语音。',title='MCP 实际生成验收',voice_id=voice['id'],project_id=media['id'],seed=42))
                assert not result.isError
                return json.loads(''.join(c.text for c in result.content if hasattr(c,'text')))
    mcp_job=completed(asyncio.run(mcp_generate()))
    report['checks']['mcp_actual_generation']=mcp_job['id']
    assert all(r['review']=='pending' for r in client.request('GET','/results'))
    report['checks']['no_automatic_approval']=True
    report['backup']=client.request('POST','/maintenance/backup')
    report['finished_at']=time.time()
    report['technical_workflows']='passed'
    save()
    print(json.dumps(dict(jobs=len(report['jobs']),export_packages=len(report['exports']),checks=list(report['checks']),human_listening='pending'),ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
