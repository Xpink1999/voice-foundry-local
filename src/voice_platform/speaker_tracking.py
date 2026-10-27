"""Offline diarization, global voice anchors and selective overlap separation.

Speaker labels are local to one run. Similarities are model scores, not identity
probabilities. Compact audition tracks never become clone references implicitly.
"""
import gc
import itertools
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from .audio import sha256, write_wav
from .reference_analysis import Analyzer, silence_metrics
from .tracking_quality import coverage, clip_stats, restore_timeline


def assemble_clips(request, folder, progress):
    """User-selected, ordered clips; bounded memory and full per-clip provenance."""
    inputs=request['assembly_inputs'];rate=inputs[0]['sample_rate']
    target=Path(folder)/'assembled.wav';position=0.;mapping=[]
    with sf.SoundFile(target,'w',samplerate=rate,channels=1,subtype='PCM_24') as out:
        for index,item in enumerate(inputs):
            source=Path(item['file'])
            if sha256(source)!=item['sha256']:raise ValueError('所选片段校验失败，原片段保留')
            pcm,sr=sf.read(source,dtype='float32')
            if sr!=rate or pcm.ndim!=1:raise ValueError('所选片段需为相同采样率的单声道音频')
            if index:
                gap=np.zeros(round(rate*request['gap_ms']/1000),dtype=np.float32)
                out.write(gap);position+=len(gap)/rate
            mapping.append(dict(source_output_id=item['id'],speaker_id=item.get('speaker_id'),
                output_start=position,output_end=position+len(pcm)/rate,source_spans=item['source_spans']))
            out.write(pcm);position+=len(pcm)/rate
            progress(100*(index+1)/len(inputs),'合并用户选择的有效语音')
    output=dict(file=str(target),label=request['assembly_name'],role='speech',stage='assemble_clips',
        kind='assembly',final=True,sample_rate=rate,channels=1,duration=position,sha256=sha256(target),
        source_spans=mapping,reference_eligible=False,review='pending',purpose=request.get('purpose','audition'))
    if request.get('purpose')=='reference':
        analyzer=Analyzer(request['config_snapshot'] if 'config_snapshot' in request else request['config'])
        pcm,_=sf.read(target,dtype='float32')
        output['transcript']=dict(analyzer.transcribe(pcm),confirmed=False,audio_sha256=output['sha256'])
        output['embedding']=analyzer.embedding(pcm)
        output['qc']=request['reference_qc']
        output['reference_state']='draft'
    return dict(outputs=[output],model_sources=request['assembly_models'],
        device='cpu',note='按用户选择顺序合并；原片段保留，合并文件不自动用作人物参考。')


def unit(value):
    value = np.asarray(value, dtype=np.float32)
    return value / max(float(np.linalg.norm(value)), 1e-8)


def activity_regions(turns, duration):
    """Sweep the actual overlapping annotation; exclusive diarization loses overlap."""
    edges = {}
    for turn in turns:
        start, end = max(0., float(turn['start'])), min(duration, float(turn['end']))
        if end <= start:
            continue
        edges.setdefault(start, []).append((turn['speaker'], 1))
        edges.setdefault(end, []).append((turn['speaker'], -1))
    active, regions, previous = {}, [], 0.
    for position in sorted(edges):
        labels = sorted(label for label, count in active.items() if count > 0)
        if labels and position > previous:
            if regions and regions[-1]['speakers'] == labels and abs(regions[-1]['end']-previous) < 1e-5:
                regions[-1]['end'] = position
            else:
                regions.append(dict(start=previous, end=position, speakers=labels))
        for label, delta in edges[position]:
            active[label] = active.get(label, 0) + delta
        previous = position
    return regions


def match_sources(embeddings, anchors, allowed, threshold, margin):
    """One-to-one matching to global anchors, including after arbitrarily long gaps."""
    scores = [{label: float(np.dot(unit(e), unit(anchors[label]))) for label in allowed if label in anchors}
              for e in embeddings]
    labels = [label for label in allowed if label in anchors]
    if not labels:return [dict(speaker=None,score=None,margin=None) for _ in embeddings]
    # Explicit unknown slots permit partial matching without inferring the missing person.
    orders=set(itertools.permutations(labels+[None]*len(embeddings),len(embeddings)))
    choices=sorted(((sum(scores[i][label]-threshold if label else 0. for i,label in enumerate(order)),order)
                    for order in orders if len([x for x in order if x])==len(set(x for x in order if x))),
                   key=lambda item:item[0],reverse=True)
    result = []
    for index, label in enumerate(choices[0][1]):
        if label is None:
            result.append(dict(speaker=None,score=None,margin=None));continue
        score = scores[index][label]
        runner_up = max((v for other, v in scores[index].items() if other != label), default=-1.)
        competing=max((s[label] for i,s in enumerate(scores) if i!=index),default=-1.)
        difference = min(score-runner_up,score-competing)
        result.append(dict(speaker=label if score >= threshold and difference >= margin else None,
                           score=score, margin=difference))
    return result


def compact_pcm(pcm, sr, spans, gap_ms=180):
    """Return independent cuts and a source/output map without rewriting source time."""
    pieces, mapping, position = [], [], 0
    gap = np.zeros(round(sr*gap_ms/1000), dtype=np.float32)
    for start, end in spans:
        first, last = max(0, round(start*sr)), min(len(pcm), round(end*sr))
        if last <= first:
            continue
        if pieces:
            pieces.append(gap)
            position += len(gap)
        part = pcm[first:last].copy()
        edge = min(round(sr*.005), len(part)//2)
        if edge:
            part[:edge] *= np.linspace(0, 1, edge)
            part[-edge:] *= np.linspace(1, 0, edge)
        mapping.append(dict(source_start=first/sr, source_end=last/sr,
                            output_start=position/sr, output_end=(position+len(part))/sr))
        pieces.append(part)
        position += len(part)
    return (np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)), mapping


def mapped_speech(spans, mapping):
    result=[]
    for a,b in spans:
        for m in mapping:
            start=max(a,m['output_start']);end=min(b,m['output_end'])
            if end>start:
                result.append(dict(source_start=m['source_start']+start-m['output_start'],
                                   source_end=m['source_start']+end-m['output_start']))
    return result


class SpeakerTracker:
    def __init__(self, config):
        self.config = config
        self.options = config['speaker_tracking']
        self.analyzer = Analyzer(config)
        self.sr = config['reference_preprocessing']['sample_rate']

    def diarize(self, pcm, count, progress):
        import os
        os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
        from pyannote.audio import Pipeline
        import torch
        path = Path(self.options['model_dir'])
        if not path.is_absolute():
            path = Path(self.config['root'])/path
        provenance = json.loads((path/'provenance.json').read_text(encoding='utf-8'))
        for entry in provenance['files']:
            if sha256(path/entry['file']) != entry['sha256']:
                raise ValueError('人物跟踪模型校验失败，请重新安装')
        progress(8, '标注人物说话时间与重叠区域')
        pipeline = Pipeline.from_pretrained(str(path))
        pipeline.to(torch.device(self.config['audio_processing']['device']))
        args = dict(num_speakers=count) if count else {}
        output = pipeline(dict(waveform=torch.from_numpy(pcm[None, :]), sample_rate=self.sr), **args)
        annotation = output.speaker_diarization
        turns = [dict(start=float(span.start), end=float(span.end), speaker=label)
                 for span, _, label in annotation.itertracks(yield_label=True)]
        del pipeline, output
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return turns, provenance

    def speech_spans(self, pcm):
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        vad = load_silero_vad(onnx=True)
        detected = get_speech_timestamps(torch.from_numpy(pcm), vad, sampling_rate=self.sr,
            return_seconds=True, min_speech_duration_ms=250, min_silence_duration_ms=300)
        return [(float(s['start']), float(s['end'])) for s in detected]

    def run(self, request, folder, progress):
        import librosa
        import torch
        torch.set_num_threads(self.config['audio_processing']['cpu_threads'])
        pcm, rate = sf.read(request['input_path'], dtype='float32', always_2d=True)
        pcm = librosa.resample(pcm.mean(axis=1), orig_sr=rate, target_sr=self.sr)
        duration = len(pcm)/self.sr
        turns, model = self.diarize(pcm, request.get('speaker_count'), progress)
        regions = activity_regions(turns, duration)
        labels = sorted({t['speaker'] for t in turns})
        if not labels:
            raise ValueError('未检测到可跟踪的人声，原件和已有结果保留')
        # Independent VAD removes background/silence without treating it as a speaker.
        speech = self.speech_spans(pcm)
        padding = self.options['edge_padding_ms']/1000
        pieces = []
        for region in regions:
            for a, b in speech:
                start, end = max(region['start'], a-padding), min(region['end'], b+padding)
                maximum = 8. if len(region['speakers']) > 1 else self.options['max_clip_seconds']
                # Short turns remain in the speaker timeline; a one-second cutoff
                # silently loses interjections and brief overlaps in conversations.
                while end-start >= self.options.get('min_turn_seconds',.15):
                    stop = min(end, start+maximum)
                    if (pieces and len(region['speakers'])==1 and pieces[-1]['speakers']==region['speakers']
                            and start-pieces[-1]['end']<=self.config['reference_preprocessing']['speech_merge_gap_seconds']
                            and stop-pieces[-1]['start']<=maximum):
                        pieces[-1]['end']=stop
                    else:
                        pieces.append(dict(start=start, end=stop, speakers=region['speakers']))
                    start = stop
        # Anchor only with non-overlap speech; never derive identity from a mixed segment.
        anchors, profiles = {}, []
        for label in labels:
            solo = sorted((r for r in pieces if r['speakers'] == [label] and r['end']-r['start'] >= 1.5),
                          key=lambda r:r['end']-r['start'], reverse=True)[:5]
            values = [self.analyzer.embedding(pcm[round(r['start']*self.sr):round(r['end']*self.sr)]) for r in solo]
            if values:
                anchors[label] = unit(np.mean([unit(e) for e in values], axis=0))
            profiles.append(dict(id=label, name='', anchor_spans=solo, anchor_count=len(solo),
                                 status='anchored' if values else 'needs_reference'))
        progress(30, '建立全程人物声纹依据，筛选独白片段')
        saved, segments, unresolved = [], [], []
        used_separators=set()
        if len(labels)>3:
            unresolved.append(dict(start=0.,end=duration,reason='speaker_count_out_of_scope',detected=len(labels)))
        separator=None
        folder = Path(folder)
        def save(audio, label, kind, spans, **extra):
            key=f'track-{len(saved)+1:04}'
            path=folder/(key+'.wav')
            write_wav(path, audio, self.sr)
            item=dict(key=key, file=str(path), label=label, role='speech', stage='track_speakers', final=True,
                      sample_rate=self.sr, channels=1, duration=len(audio)/self.sr, sha256=sha256(path),
                      kind=kind, source_spans=spans, **extra)
            saved.append(item)
            return item
        for index, piece in enumerate(pieces):
            start, end = piece['start'], piece['end']
            audio = pcm[round(start*self.sr):round(end*self.sr)]
            if len(piece['speakers']) == 1:
                label=piece['speakers'][0]
                score=float(np.clip(np.dot(unit(self.analyzer.embedding(audio)), anchors[label]),-1.,1.)) if label in anchors and len(audio)>=self.sr else None
                candidates=[(audio, label, score, None, 'solo')]
            elif len(piece['speakers']) in {2,3}:
                from .processing_engines import ProcessingEngines
                if separator is None:separator=ProcessingEngines(self.config)
                # Context gives the separator and voice encoder evidence around a
                # brief interruption. Only the actual overlapping span is retained.
                context_start=max(0.,start-.7);context_end=min(duration,end+.7)
                context_audio=pcm[round(context_start*self.sr):round(context_end*self.sr)]
                try:
                    if len(piece['speakers'])==3:
                        split=separator.separate_three(context_audio[None,:],self.sr,lambda _:None)
                    else:split=separator.separate(context_audio[None, :], self.sr, lambda _:None,retain=True)
                    used_separators.add(len(piece['speakers']))
                except (FileNotFoundError,ValueError,ImportError) as error:
                    unresolved.append(dict(start=start,end=end,speakers=piece['speakers'],reason='separator_unavailable',detail=str(error)))
                    continue
                split=[(name,separator.resample(audio,rate,self.sr),self.sr) for name,audio,rate in split]
                matches=match_sources([self.analyzer.embedding(s[1]) for s in split], anchors, piece['speakers'],
                                      self.options['match_threshold'], self.options['match_margin'])
                first,last=round((start-context_start)*self.sr),round((end-context_start)*self.sr)
                candidates=[(s[1][first:last], m['speaker'], m['score'], m['margin'], 'overlap') for s,m in zip(split,matches)]
            else:
                unresolved.append(dict(start=start, end=end, speakers=piece['speakers'], reason='more_than_two_overlapping'))
                continue
            for audio,label,score,margin,kind in candidates:
                own_speech=self.speech_spans(audio)
                cuts=[(max(0.,a-padding),min(len(audio)/self.sr,b+padding)) for a,b in own_speech]
                # Merge padded neighbouring ranges to avoid duplicating their overlap.
                merged=[]
                for a,b in cuts:
                    if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
                    else:merged.append((a,b))
                cuts=merged
                cleaned,mapping=compact_pcm(audio,self.sr,cuts,self.options.get('trim_pause_ms',120))
                if len(cleaned):
                    audio=cleaned
                    mapping=[dict(m,source_start=m['source_start']+start,source_end=m['source_end']+start) for m in mapping]
                else:
                    mapping=[dict(source_start=start,source_end=end,output_start=0.,output_end=len(audio)/self.sr)]
                transcript=self.analyzer.transcribe(audio) if len(audio)>=self.sr else dict(text='',confirmed=False,
                    status='too_short_for_transcription',low_confidence=True,source='none')
                warnings=[]
                if kind=='overlap':warnings.append('分离片段需检查串音')
                if len(audio)<5*self.sr:warnings.append('短于推荐 5 秒，建议保留为备选并试听')
                if score is not None and score<self.options['match_threshold']:warnings.append('声纹匹配偏弱，需试听确认人物')
                item=save(audio, label or '待确认', 'clip', mapping,
                          speaker_id=label, origin=kind, similarity=score, match_margin=margin,
                          transcript=transcript,embedding=self.analyzer.embedding(audio),
                          recommended=bool(label and kind=='solo' and 5<=len(audio)/self.sr<=30
                              and score is not None and score>=self.options['match_threshold'] and not transcript['low_confidence']),
                          review='pending', warnings=warnings,revision=1,assignment_confirmed=False,
                          native_sample_rate=8000 if kind=='overlap' and len(piece['speakers'])==3 else self.sr,
                          speech_spans=mapped_speech(self.speech_spans(audio),mapping))
                item['speech_stats']=clip_stats(item)
                segments.append(dict(output_key=item['key'],start=start,end=end,speaker_id=label,origin=kind,
                                     similarity=score,match_margin=margin,review='pending'))
                if not label:
                    unresolved.append(dict(start=start,end=end,output_key=item['key'],reason='ambiguous_voice_match'))
            progress(30+50*(index+1)/max(1,len(pieces)), '按全程声纹归属独白与重叠片段')
        if separator:separator.close()
        # Preserve the solo-only product and publish a separately named complete mapped track.
        for profile in profiles:
            selected=[s for s in segments if s['speaker_id']==profile['id'] and s['origin']=='solo']
            spans=[(s['start'],s['end']) for s in selected]
            profile['solo_seconds']=sum(b-a for a,b in spans)
            profile['overlap_seconds']=sum(s['end']-s['start'] for s in segments
                if s['speaker_id']==profile['id'] and s['origin']=='overlap')
            if spans:
                timeline=np.zeros_like(pcm)
                for a,b in spans:
                    first,last=round(a*self.sr),round(b*self.sr)
                    timeline[first:last]=pcm[first:last]
                profile['timeline_key']=save(timeline,profile['id']+' · 独白时间轴','timeline',
                    [dict(source_start=a,source_end=b) for a,b in spans],speaker_id=profile['id'],
                    reference_eligible=False,timeline_type='solo_timeline',review='pending')['key']
            clips=[o for o in saved if o.get('kind')=='clip' and o.get('speaker_id')==profile['id']]
            full=restore_timeline(clips,len(pcm),self.sr,lambda c:sf.read(c['file'],dtype='float32')[0])
            profile['full_timeline_key']=save(full,profile['id']+' · 完整人物时间轴','full_speaker_timeline',
                [dict(output_key=c['key'],source_spans=c['source_spans']) for c in clips],
                speaker_id=profile['id'],reference_eligible=False,review='pending',
                completeness='partial' if unresolved else 'complete',unresolved=unresolved)['key']
            profile['recommended_keys']=[o['key'] for o in saved if o.get('speaker_id')==profile['id'] and o.get('recommended')]
            profile['clip_count']=sum(s['speaker_id']==profile['id'] for s in segments)
            profile['file_seconds']=sum(c['duration'] for c in clips)
            profile['effective_seconds']=coverage([s for c in clips for s in c['speech_spans']])
            profile['effective_seconds_estimated']=True
        similarities=[dict(left=a,right=b,cosine=float(np.dot(anchors[a],anchors[b])))
                      for a,b in itertools.combinations(anchors,2)]
        progress(92,'整理人物试听、有效语音与来源时间映射')
        overlap_seconds=sum(r['end']-r['start'] for r in regions if len(r['speakers'])>1)
        sources=dict(diarization=model,speaker=self.analyzer.models()['speaker_dir'])
        if used_separators:
            from .processing_engines import ProcessingEngines
            for count in used_separators:
                key='separation_dir' if count==2 else 'three_separation_dir'
                path=separator.source(key)
                if (path/'provenance.json').is_file():sources[key]=json.loads((path/'provenance.json').read_text(encoding='utf-8'))
        for key in ('whisper_dir','speaker_dir'):
            path=self.analyzer.path(key)/'provenance.json'
            if path.is_file():sources[key]=json.loads(path.read_text(encoding='utf-8'))
        return dict(outputs=saved,model_sources=sources,
            device=self.config['audio_processing']['device'],
            note='人物编号仅对本次录音有效；声纹分数不是身份概率。片段去除长空白，合并由用户选择；参考片段独立保存。重叠结果需检查串音。',
            tracking=dict(speakers=profiles,segments=segments,turns=turns,unresolved=unresolved,
                speaker_similarities=similarities,duration=duration,overlap_seconds=overlap_seconds,
                silence=silence_metrics(pcm,self.sr),score_type='Resemblyzer cosine; not calibrated probability',
                model='pyannote/speaker-diarization-community-1',review='pending'))
