"""Local audio analysis and transparent, approximate ranking; no implicit concatenation."""
import gc
import json
import math
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
import numpy as np
import soundfile as sf
from .audio import sha256, write_wav

def intervals(speech, duration, config):
    target=config['target_clip_seconds'];gap=config['speech_merge_gap_seconds']
    groups=[]
    for item in speech:
        start=max(0,float(item['start'])-.12);end=min(duration,float(item['end'])+.12)
        label=item.get('speaker_label','unknown')
        if groups and label==groups[-1][2] and start-groups[-1][1]<=gap and end-groups[-1][0]<=target:
            groups[-1][1]=end
        else:groups.append([start,end,label])
    clips=[]
    for start,end,label in groups:
        while end-start>target:
            clips.append((start,start+target));start+=target
        if end-start>=.5:clips.append((start,end))
    # Prefer useful durations before imposing a bounded candidate count, retain source offsets.
    ranked=sorted(clips,key=lambda p:(p[1]-p[0]>=config['recommended_min_seconds'],p[1]-p[0]),reverse=True)
    return sorted(ranked[:config['max_candidates']]),len(clips)

def silence_metrics(y,sr):
    frame=max(1,round(sr*.02));length=len(y)//frame
    rms=np.sqrt(np.mean(y[:length*frame].reshape(length,frame)**2,axis=1)) if length else np.array([])
    mask=rms<10**(-50/20)
    longest=current=0
    for silent in mask:
        current=current+1 if silent else 0;longest=max(longest,current)
    return dict(ratio=float(mask.mean()) if len(mask) else 1.,longest_seconds=round(longest*.02,3),threshold_dbfs=-50)

def cluster(embeddings,threshold):
    centers=[];counts=[];labels=[]
    for value in embeddings:
        e=np.asarray(value,dtype=np.float32);e/=max(float(np.linalg.norm(e)),1e-8)
        similarities=[float(np.dot(e,c)) for c in centers]
        if similarities and max(similarities)>=threshold:
            label=int(np.argmax(similarities));center=centers[label]*counts[label]+e
            centers[label]=center/max(float(np.linalg.norm(center)),1e-8);counts[label]+=1
        else:label=len(centers);centers.append(e);counts.append(1)
        labels.append(label)
    return labels,centers

@lru_cache(maxsize=1)
def text_converter():
    from opencc import OpenCC
    return OpenCC('t2s')

def char_error(expected,actual):
    # ASR may choose traditional Chinese despite a simplified prompt. Do not count script variants as pronunciation errors.
    normalize=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',text_converter().convert(unicodedata.normalize('NFKC',s)).lower(),flags=re.UNICODE).replace('_','')
    a,b=normalize(expected),normalize(actual)
    if not a:return 1.
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        next_row=[i]
        for j,y in enumerate(b,1):next_row.append(min(next_row[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=next_row
    return row[-1]/len(a)

class Analyzer:
    def __init__(self,config):
        self.config=config;self.options=config['reference_preprocessing'];self.root=Path(config['root'])
        self.sr=self.options['sample_rate'];self.asr=None;self.encoder=None;self.classifier=None;self.extractor=None

    def path(self,key):
        p=Path(self.options[key]);return p if p.is_absolute() else self.root/p

    def models(self):
        return {key:json.loads((self.path(key)/'provenance.json').read_text(encoding='utf-8')) for key in ('whisper_dir','classifier_dir','speaker_dir')}

    def transcribe(self,y):
        if self.asr is None:
            from faster_whisper import WhisperModel
            self.asr=WhisperModel(str(self.path('whisper_dir')),device='cpu',compute_type='int8',cpu_threads=self.options['cpu_threads'],local_files_only=True)
        segments,info=self.asr.transcribe(y,beam_size=5,condition_on_previous_text=False,vad_filter=False,temperature=0,word_timestamps=False)
        values=[dict(start=s.start,end=s.end,text=s.text.strip(),avg_logprob=s.avg_logprob,no_speech_prob=s.no_speech_prob) for s in segments]
        text=''.join(s['text'] for s in values) if info.language in {'zh','ja'} else ' '.join(s['text'] for s in values)
        return dict(text=text,language=info.language,language_probability=info.language_probability,segments=values,
                    confirmed=False,source='faster-whisper-small',status='automatic_unconfirmed',
                    low_confidence=not text or any(s['avg_logprob']<-1 or s['no_speech_prob']>.6 for s in values))

    def embedding(self,y):
        if self.encoder is None:
            source=str(self.root/'vendor/Resemblyzer')
            if source not in sys.path:sys.path.insert(0,source)
            from resemblyzer import VoiceEncoder
            self.encoder=VoiceEncoder(device='cpu',weights_fpath=self.path('speaker_dir')/'pretrained.pt',verbose=False)
        rms=float(np.sqrt(np.mean(y**2)))
        normalized=y*min(10.,.03/max(rms,1e-7))
        return self.encoder.embed_utterance(normalized.astype(np.float32)).astype(float).tolist()

    def classify(self,y):
        import torch
        if self.classifier is None:
            from transformers import AutoFeatureExtractor,AutoModelForAudioClassification
            self.extractor=AutoFeatureExtractor.from_pretrained(self.path('classifier_dir'),local_files_only=True)
            self.classifier=AutoModelForAudioClassification.from_pretrained(self.path('classifier_dir'),local_files_only=True).eval()
        inputs=self.extractor(y,sampling_rate=self.sr,return_tensors='pt')
        with torch.inference_mode():scores=self.classifier(**inputs).logits[0].sigmoid().cpu().numpy()
        labels=self.classifier.config.id2label
        by_name={labels[i]:float(v) for i,v in enumerate(scores)}
        music=max((v for k,v in by_name.items() if 'music' in k.lower() or k=='Musical instrument'),default=0)
        noise=max((v for k,v in by_name.items() if 'noise' in k.lower() or k in {'Static','Hiss','Hum','Buzz'}),default=0)
        conversation=max((by_name.get(k,0) for k in ('Conversation','Babbling','Hubbub, speech noise, speech babble','Crowd')),default=0)
        return dict(music_score=music,noise_score=noise,conversation_score=conversation,speech_score=max(by_name.get(k,0) for k in ('Speech','Male speech, man speaking','Female speech, woman speaking','Child speech, kid speaking','Speech synthesizer')),
                    top_labels=sorted(by_name.items(),key=lambda x:x[1],reverse=True)[:6])

    def analyze(self,recording,output,progress):
        import torch
        from silero_vad import load_silero_vad,get_speech_timestamps
        torch.set_num_threads(self.options['cpu_threads'])
        y,sr=sf.read(recording['analysis_path'],dtype='float32');assert sr==self.sr and y.ndim==1
        duration=len(y)/sr
        progress(5,'识别人声与静音')
        vad=load_silero_vad(onnx=True)
        detected=get_speech_timestamps(torch.from_numpy(y),vad,sampling_rate=sr,return_seconds=True,min_speech_duration_ms=250,min_silence_duration_ms=250)
        speech=[dict(start=float(s['start']),end=float(s['end'])) for s in detected]
        del vad
        speaker_windows=[];speaker_embeddings=[]
        for segment in speech:
            for start in np.arange(segment['start'],segment['end'],2.5):
                end=min(segment['end'],start+2.5)
                if end-start<1:continue
                speaker_embeddings.append(self.embedding(y[round(start*sr):round(end*sr)]))
                speaker_windows.append(dict(start=float(start),end=float(end)))
        speaker_labels,speaker_centers=cluster(speaker_embeddings,self.options['speaker_similarity_threshold'])
        for w,label in zip(speaker_windows,speaker_labels):w['speaker_label']=f'S{label+1}'
        # Split at detected changes. These are anonymous, approximate turn labels, not person identities.
        turns=[]
        for segment in speech:
            inside=[w for w in speaker_windows if w['start']>=segment['start'] and w['end']<=segment['end']]
            if not inside:turns.append(dict(segment,speaker_label='unknown'));continue
            cursor=segment['start']
            for i,w in enumerate(inside):
                stop=inside[i+1]['start'] if i+1<len(inside) else segment['end']
                if turns and turns[-1]['speaker_label']==w['speaker_label'] and cursor-turns[-1]['end']<.01:
                    turns[-1]['end']=stop
                else:turns.append(dict(start=cursor,end=stop,speaker_label=w['speaker_label']))
                cursor=stop
        for index,turn in enumerate(turns):
            if turn['speaker_label']!='unknown':continue
            previous=turns[index-1] if index else None;following=turns[index+1] if index+1<len(turns) else None
            nearby=[t for t in (previous,following) if t and t['speaker_label']!='unknown' and min(abs(turn['start']-t['end']),abs(t['start']-turn['end']))<=1.2]
            if nearby and len({t['speaker_label'] for t in nearby})==1:turn['speaker_label']=nearby[0]['speaker_label']
        cuts,total_candidates=intervals(turns,duration,self.options)
        windows=[]
        for index,start in enumerate(np.arange(0,duration,10.0)):
            pcm=y[round(start*sr):round(min(duration,start+10)*sr)]
            tag=self.classify(pcm) if float(np.max(np.abs(pcm),initial=0))>.001 else dict(music_score=0.,noise_score=0.,conversation_score=0.,speech_score=0.,top_labels=[])
            windows.append(dict(start=float(start),end=float(min(duration,start+10)),**tag))
            progress(10+25*(index+1)/max(1,math.ceil(duration/10)),'检测背景音乐与噪声')
        clips=[]
        for index,(start,end) in enumerate(cuts):
            pcm=y[round(start*sr):round(end*sr)]
            path=Path(output)/f'clip-{index+1:03}.wav';write_wav(path,pcm,sr)
            transcript=self.transcribe(pcm)
            embedding=self.embedding(pcm)
            local_labels={w['speaker_label'] for w in speaker_windows if w['start']<end-.2 and w['end']>start+.2}
            centers=list(local_labels)
            relevant=[self.classify(pcm[i:i+10*sr]) for i in range(0,len(pcm),10*sr)]
            music=max((w['music_score'] for w in relevant),default=0);noise=max((w['noise_score'] for w in relevant),default=0)
            speech_score=max((w['speech_score'] for w in relevant),default=0)
            silence=silence_metrics(pcm,sr);clip_ratio=float(np.mean(np.abs(pcm)>=.999))
            warnings=[]
            if end-start<self.options['recommended_min_seconds']:warnings.append('短于推荐 5 秒，克隆稳定性需试听')
            if music>=self.options['music_threshold']:warnings.append('疑似背景音乐')
            if noise>=self.options['noise_threshold']:warnings.append('疑似噪声')
            if len(centers)>1:warnings.append('候选中检测到疑似多人或声线变化')
            if silence['longest_seconds']>=self.options['long_silence_seconds']:warnings.append('存在较长静音')
            if transcript['low_confidence']:warnings.append('自动转写置信度偏低，请校对')
            if speech_score<.15:warnings.append('声音分类器对人声置信度低，可能为误检，请勿直接作为主参考')
            if clip_ratio>.001:warnings.append('可能存在削波失真')
            quality=max(0.,min(1.,1-.3*music-.2*noise-.2*silence['ratio']-.2*(len(centers)>1)-.1*(end-start<5)-.25*(speech_score<.15)-min(.2,clip_ratio*10)))
            clips.append(dict(start=start,end=end,file=str(path),duration=end-start,sample_rate=sr,sha256=sha256(path),transcript=transcript,speaker_labels=sorted(local_labels),
                embedding=embedding,quality=dict(score=quality,music_score=music,noise_score=noise,speech_score=speech_score,speaker_clusters=len(centers),silence=silence,clipping_ratio=clip_ratio,warnings=warnings)))
            progress(35+60*(index+1)/max(1,len(cuts)),f'转写并分析候选 {index+1}/{len(cuts)}')
        gc.collect()
        reliable_labels={label for c in clips if c['quality']['speech_score']>=.15 and not c['transcript']['low_confidence'] for label in c['speaker_labels']}
        summary=dict(duration=duration,recommended_seconds=[5,30],speech_segments=speech,silence=silence_metrics(y,sr),
            music_suspected=any(w['music_score']>=self.options['music_threshold'] for w in windows),
            noise_suspected=any(w['noise_score']>=self.options['noise_threshold'] for w in windows),
            estimated_speakers=len(reliable_labels),raw_voice_clusters=len(speaker_centers),multiple_speakers_suspected=len(reliable_labels)>1,speaker_windows=speaker_windows,speaker_turns=turns,
            speaker_coverage='全部 VAD 人声中至少 1 秒的 2.5 秒窗口；边界为近似值，不是身份鉴定，无法保证分离重叠人声',
            classifier_windows=windows,candidate_count_total=total_candidates,candidate_limit=self.options['max_candidates'],
            detection_note='模型分数未经过本地场景校准；未检出不代表绝对干净。没有进行人声分离或拼接。',
            models=self.models())
        return dict(summary=summary,clips=clips)

    def score_comparison(self,items,text,progress):
        scored=[]
        for index,item in enumerate(items):
            outputs=[]
            for path in item['audio_paths']:
                import librosa
                y,_=librosa.load(path,sr=self.sr,mono=True)
                transcription=self.transcribe(y)
                outputs.append(dict(embedding=self.embedding(y),transcript=transcription['text'],cer=char_error(text,transcription['text'])))
            ref=np.asarray(item['embedding'])
            similarities=[float(np.dot(ref,o['embedding'])/max(np.linalg.norm(ref)*np.linalg.norm(o['embedding']),1e-8)) for o in outputs]
            agreement=[float(np.dot(a['embedding'],b['embedding'])) for i,a in enumerate(outputs) for b in outputs[i+1:]]
            similarity=float(np.mean(similarities));stability=float(np.mean(agreement));cer=float(np.mean([o['cer'] for o in outputs]))
            score=.45*similarity+.25*(1-min(cer,1))+.2*stability+.1*item.get('quality_score',.5)
            scored.append(dict(reference_id=item['reference_id'],score=score,speaker_similarity=similarity,seed_consistency=stability,
                asr_character_error=cer,generated_transcripts=[o['transcript'] for o in outputs],result_ids=item['result_ids']))
            progress(100*(index+1)/len(items),'比较克隆相似度、跨种子一致性和文字可懂度')
        scored.sort(key=lambda x:x['score'],reverse=True)
        return dict(ranking=scored,recommended_reference_id=scored[0]['reference_id'] if scored else None,
                    note='自动推荐使用 Resemblyzer 余弦分数、跨种子一致性与 ASR 字符误差（忽略标点、大小写、全半角及繁简字差异）；不代替听感，不自动批准或切换主参考。')
