"""Read-only verification of already generated real-model assets; never approves audio."""
import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import httpx
import numpy as np
import soundfile as sf
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from voice_platform.audio import sha256
from voice_platform.config import ROOT


async def check_mcp(recording_id,comparison_id):
    records=[]
    for folder in ('game_project','media_project'):
        directory=ROOT/'examples'/folder
        parameters=StdioServerParameters(command=sys.executable,args=['-m','voice_platform.mcp_server'],cwd=str(directory))
        async with stdio_client(parameters) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                initialized=await session.initialize()
                names=[tool.name for tool in (await session.list_tools()).tools]
                assert {'voice_upload_recording','voice_recording','voice_save_reference_clips','voice_compare_references','voice_reference_comparison'}<=set(names)
                assert not any('approve' in name for name in names)
                for name,body in [('voice_recording',{'recording_id':recording_id}),('voice_reference_comparison',{'comparison_id':comparison_id})]:
                    result=await session.call_tool(name,body);assert not result.isError
                    text=''.join(c.text for c in result.content if hasattr(c,'text'))
                    assert 'succeeded' in text
                records.append(dict(cwd=str(directory),server=initialized.serverInfo.model_dump(),tools=names,recording_and_comparison_calls=True))
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording-id',required=True)
    parser.add_argument('--comparison-id',required=True)
    parser.add_argument('--hifi-result-id',required=True)
    parser.add_argument('--fixture',required=True)
    args=parser.parse_args()
    client=httpx.Client(base_url='http://127.0.0.1:8961/api/v1',timeout=30)
    def get(route):
        response=client.get(route);response.raise_for_status();return response.json()
    recording=get('/recordings/'+args.recording_id)
    assert recording['status']=='succeeded'
    original=ROOT/'data'/recording['original_path']
    assert sha256(original)==sha256(args.fixture)==recording['original_sha256']
    response=client.get('/recordings/'+recording['id']+'/original');assert response.content==original.read_bytes()
    decoded,sr=sf.read(ROOT/'data'/recording['analysis_path'],dtype='float32')
    clips=[]
    for clip in recording['candidates']:
        path=ROOT/'data'/clip['path'];pcm,rate=sf.read(path,dtype='float32')
        expected=decoded[round(clip['start']*sr):round(clip['end']*sr)]
        assert rate==sr and len(pcm)==len(expected) and np.max(np.abs(pcm-expected))<2e-7
        assert sha256(path)==clip['sha256']
        clips.append({k:clip[k] for k in ('id','start','end','duration','speaker_labels','saved','quality','transcript')})
    assert len([clip for clip in clips if clip['saved']])==2
    summary=recording['summary']
    assert summary['estimated_speakers']==2 and summary['music_suspected'] and summary['noise_suspected'] and summary['silence']['longest_seconds']>=3
    comparison=get('/reference-comparisons/'+args.comparison_id)
    assert comparison['status']=='succeeded' and len(comparison['ranking'])==2
    assert '繁简' in comparison['note']
    generated=[]
    for reference_id,job_ids in comparison['job_mapping'].items():
        assert len(job_ids)==2
        for job_id in job_ids:
            job=get('/jobs/'+job_id);assert job['status']=='succeeded'
            result=get('/results/'+job['results'][0])
            assert result['review']=='pending' and result['reference_snapshot']['id']==reference_id
            assert result['reference_snapshot']['sha256']==next(c['sha256'] for c in recording['candidates'] if c['id']==reference_id)
            path=ROOT/'data'/result['path'];assert sha256(path)==result['sha256'] and sf.info(path).duration>0
            generated.append({k:result[k] for k in ('id','job_id','duration','sha256','review')})
    voice=get('/voices/'+comparison['voice_id'])
    assert voice['reference_id']==comparison['recommended_reference_id']
    assert set(comparison['reference_ids'])<=set(voice['reference_ids']) and len(voice['reference_scenarios'])==2
    assert voice['status']=='draft' and voice['reference_confirmed'] is False
    hifi=get('/results/'+args.hifi_result_id)
    assert hifi['parameters']['clone_mode']=='hifi' and hifi['reference_snapshot']['transcript']['text']
    assert hifi['parameters']['effective_style']=='' and hifi['pipeline']['control_note']
    assert hifi['reference_snapshot']['transcript']['confirmed'] is False and hifi['review']=='pending'
    assert sha256(ROOT/'data'/hifi['path'])==hifi['sha256'] and sf.info(ROOT/'data'/hifi['path']).duration>0
    cli=[]
    for folder in ('game_project','media_project'):
        directory=ROOT/'examples'/folder
        result=subprocess.run([sys.executable,'-m','voice_platform.cli','recording',recording['id']],cwd=directory,capture_output=True,text=True,encoding='utf-8',check=True)
        value=json.loads(result.stdout);assert value['id']==recording['id'] and value['status']=='succeeded'
        cli.append(dict(cwd=str(directory),same_recording=value['id'],status=value['status']))
    mcp=asyncio.run(check_mcp(recording['id'],comparison['id']))
    output=dict(verified_at=datetime.now(timezone.utc).isoformat(),scope='controlled synthetic fixture, live CPU analysis, actual RTX 4090 VoxCPM2 generation and HTTP/CLI/MCP; no human listening acceptance',
        health=get('/health'),recording_id=recording['id'],original_sha256=recording['original_sha256'],original_bytes_preserved=True,
        clips_are_exact_contiguous_source_ranges=True,summary=summary,clips=clips,comparison={k:v for k,v in comparison.items() if k!='reference_snapshots'},
        generated_results=generated,voice={k:voice[k] for k in ('id','version','reference_id','reference_ids','reference_scenarios','status','reference_confirmed')},
        hifi_result={k:hifi[k] for k in ('id','duration','sha256','review','parameters','reference_snapshot')},cli=cli,mcp=mcp)
    target=ROOT/'docs/evidence/reference-preprocessing/runtime-verification.json'
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(evidence=str(target),original_preserved=True,independent_clips=len(clips),reference_comparison_outputs=len(generated),hifi_duration=hifi['duration'],mcp_tools=len(mcp[0]['tools']),workspaces=len(mcp),all_audio_pending=True),ensure_ascii=False))


if __name__=='__main__':main()
