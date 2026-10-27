"""Short-lived CPU worker: dependencies and model memory are isolated from the TTS process."""
import json
import os
import sys
import time
from pathlib import Path
from .reference_analysis import Analyzer


def write_progress(path,percent,message):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(progress=round(percent,1),message=message),ensure_ascii=False),encoding='utf-8')
    # Windows readers/AV can briefly hold the destination without delete sharing.
    # Progress is advisory and must never turn a completed neural result into a failure.
    for attempt in range(6):
        try:temporary.replace(path);return True
        except PermissionError:
            if attempt<5:time.sleep(.01*(attempt+1))
    return False

def main():
    if os.environ.get('VOICE_WORKER_OWNED') == '1' and sys.stdin.buffer.readline() != b'start\n':
        return
    source=Path(sys.argv[1]);request=json.loads(source.read_text(encoding='utf-8'))
    progress_path=source.parent/'progress.json'
    def progress(percent,message):
        write_progress(progress_path,percent,message)
    if request['mode']=='assemble':
        from .speaker_tracking import assemble_clips
        result=assemble_clips(request,source.parent,progress)
    elif request['mode']=='track':
        from .processing_readiness import verify_frozen
        verify_frozen(request.get('tracking_model_snapshots',{}))
        from .speaker_tracking import SpeakerTracker
        result=SpeakerTracker(request['config']).run(request,source.parent,progress)
    elif request['mode']=='process':
        from .processing_engines import ProcessingEngines
        result=ProcessingEngines(request['config']).process(request,source.parent,progress)
    else:
        analyzer=Analyzer(request['config'])
        if request['mode']=='analyze':result=analyzer.analyze(request['recording'],source.parent,progress)
        else:result=analyzer.score_comparison(request['items'],request['text'],progress)
    (source.parent/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    progress(100,'处理完成')

if __name__=='__main__':main()
