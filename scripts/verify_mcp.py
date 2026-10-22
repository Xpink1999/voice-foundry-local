import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from voice_platform.config import ROOT

async def main():
    records=[]
    for directory in (ROOT/'examples/game_project',ROOT/'examples/media_project'):
        directory.mkdir(parents=True,exist_ok=True)
        params=StdioServerParameters(command=sys.executable,args=['-m','voice_platform.mcp_server'],cwd=str(directory))
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                initialized=await session.initialize()
                tools=await session.list_tools()
                names=[t.name for t in tools.tools]
                assert 'voice_generate' in names and 'voice_export' in names
                assert not any('approve' in n or 'review' in n for n in names)
                response=await session.call_tool('voice_models',{})
                assert not response.isError
                content=''.join(c.text for c in response.content if hasattr(c,'text'))
                assert 'VoxCPM2' in content
                voices=await session.call_tool('voice_library',{})
                assert not voices.isError
                records.append(dict(cwd=str(directory),server=initialized.serverInfo.model_dump(),tools=names,models_called=True,voices_called=True))
    target=ROOT/'docs/evidence/mcp-verification.json'
    target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(cross_workspaces=len(records),tools=len(records[0]['tools']),protocol='stdio MCP SDK handshake and live HTTP-backed tool calls'),ensure_ascii=False))

if __name__=='__main__':
    asyncio.run(main())
