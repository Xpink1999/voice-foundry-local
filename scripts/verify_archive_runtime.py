"""Exercise archive/restore for explicitly supplied completed test jobs, keep them archived."""
import argparse
import asyncio
import copy
import json
import subprocess
import sys
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
import httpx
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from voice_platform.config import ROOT,load_config
from voice_platform.store import Store
from voice_platform.service import Platform,TERMINAL
from voice_platform.audio import sha256


async def archive_mcp(ids):
    parameters=StdioServerParameters(command=sys.executable,args=['-m','voice_platform.mcp_server'],cwd=str(ROOT/'examples/media_project'))
    async with stdio_client(parameters) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            tools=[t.name for t in (await session.list_tools()).tools]
            assert 'voice_archive_jobs' in tools
            result=await session.call_tool('voice_archive_jobs',{'job_ids':ids})
            assert not result.isError
            return dict(tool='voice_archive_jobs',tools=len(tools),cwd=str(ROOT/'examples/media_project'),succeeded=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--job-ids',nargs='+',required=True);args=parser.parse_args()
    client=httpx.Client(base_url='http://127.0.0.1:8961/api/v1',timeout=30)
    def get(route):
        response=client.get(route);response.raise_for_status();return response.json()
    jobs=[get('/jobs/'+j) for j in args.job_ids]
    assert all(j['status'] in TERMINAL for j in jobs)
    results=[get('/results/'+r) for j in jobs for r in j['results']]
    fingerprints={r['id']:sha256(ROOT/'data'/r['path']) for r in results}
    mcp=asyncio.run(archive_mcp(args.job_ids))
    assert all(get('/jobs/'+j)['archived_at'] for j in args.job_ids)
    active_ids={j['id'] for j in get('/jobs')};assert not active_ids.intersection(args.job_ids)
    assert set(args.job_ids)<={j['id'] for j in get('/jobs?archived=true')}
    response=client.post('/jobs/restore',json={'job_ids':args.job_ids});response.raise_for_status()
    assert all(not get('/jobs/'+j).get('archived_at') for j in args.job_ids)
    # CLI from a second project reuses the same service; no project installation.
    command=[sys.executable,'-m','voice_platform.cli','archive-job',args.job_ids[0]]
    result=subprocess.run(command,cwd=ROOT/'examples/game_project',capture_output=True,text=True,encoding='utf-8',check=True)
    assert json.loads(result.stdout)['assets_preserved']
    response=client.post('/jobs/archive',json={'job_ids':args.job_ids});response.raise_for_status()
    for before in results:
        assert get('/results/'+before['id'])==before
        assert sha256(ROOT/'data'/before['path'])==fingerprints[before['id']]
        assert client.get('/results/'+before['id']+'/audio').status_code==200
    # Verify age policy against a private online database snapshot. Never rewrite production timestamps.
    folder=ROOT/'runtime'/('archive-policy-'+str(uuid.uuid4()));folder.mkdir(parents=True)
    cfg=copy.deepcopy(load_config());cfg['data_dir']=str(folder)
    Store(ROOT/'data').backup(folder/'platform.sqlite3')
    platform=Platform(cfg);before_results=platform.store.list('results')
    before_jobs=platform.store.jobs()['items'];future=datetime.now(timezone.utc)+timedelta(days=8)
    expected={j['id'] for j in before_jobs if j['status'] in TERMINAL}
    archived=set(platform.archive_due(force=True,clock=future));assert archived==expected
    assert platform.store.list('results')==before_results
    report=dict(verified_at=datetime.now(timezone.utc).isoformat(),job_ids=args.job_ids,manual_archive_restore=True,mcp=mcp,
        cli_cwd=str(ROOT/'examples/game_project'),audio_and_review_records_unchanged=True,fingerprints=fingerprints,
        age_policy=dict(days=cfg.get('task_archive_after_days',7),snapshot=str(folder),controlled_clock=future.isoformat(),archived_count=len(archived),
            scope='private SQLite snapshot with injected future clock; not a seven-day wall-clock soak'),
        current_count=get('/jobs/page')['total'],archived_count=get('/jobs/page?archived=true')['total'])
    target=ROOT/'docs/evidence/reference-preprocessing/archive-runtime-verification.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
