"""Offline restoration adapters. Official neural code is imported only inside the worker."""
import gc
import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import soundfile as sf
from .audio import sha256,write_wav


def namespace(name,path):
    # Avoid importing vendor demo/training/video dependencies. Relative neural imports remain unchanged.
    if name not in sys.modules:
        module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module


def overlap_add(signal,rate,seconds,predict,progress,align_speakers=False):
    """Bound memory; crossfade continuous time windows, align anonymous outputs on overlaps."""
    signal=np.asarray(signal,dtype=np.float32)
    if signal.ndim==1:signal=signal[None,:]
    window=round(rate*seconds);stride=window//2;length=signal.shape[-1]
    starts=list(range(0,max(1,length-window+1),stride))
    if starts[-1]+window<length:starts.append(max(0,length-window))
    starts=sorted(set(starts));result=None;weight=np.zeros(length,dtype=np.float32)
    for index,start in enumerate(starts):
        size=min(window,length-start);chunk=signal[:,start:start+size]
        chunk=np.pad(chunk,((0,0),(0,window-size)))
        outputs=np.asarray(predict(chunk),dtype=np.float32)
        if outputs.ndim==1:outputs=outputs[None,:]
        outputs=outputs[...,:size]
        if outputs.shape[-1]!=size or not np.isfinite(outputs).all():raise ValueError('处理模型返回长度不匹配或非有限采样')
        if result is None:result=np.zeros((len(outputs),length),dtype=np.float32)
        if align_speakers and len(outputs)==2 and index:
            overlap=min(window//2,size)
            previous=result[:,start:start+overlap]/np.maximum(weight[start:start+overlap],1e-8)
            current=outputs[:,:overlap]
            def similarity(a,b):return float(np.dot(a,b)/max(np.linalg.norm(a)*np.linalg.norm(b),1e-8))
            direct=sum(similarity(previous[i],current[i]) for i in range(2))
            reverse=sum(similarity(previous[i],current[1-i]) for i in range(2))
            if reverse>direct:outputs=outputs[::-1]
        fade=np.ones(size,dtype=np.float32);edge=min(window//2,size//2)
        if index:fade[:edge]=np.linspace(.001,1,edge)
        if index+1<len(starts):fade[-edge:]=np.linspace(1,.001,edge)
        result[:,start:start+size]+=outputs*fade;weight[start:start+size]+=fade
        progress((index+1)/len(starts))
    return result/np.maximum(weight,1e-8)


def restore_source_scale(outputs,mixture):
    """BSS estimates have arbitrary scale. Fit their sum to the observed mixture without peak amplification."""
    values=outputs.astype(np.float64);rms=np.sqrt(np.mean(values**2,axis=1)).clip(1e-12)
    normalized=values/rms[:,None]
    gram=normalized@normalized.T/values.shape[-1]
    rhs=normalized@mixture.astype(np.float64)/values.shape[-1]
    weights=np.linalg.solve(gram+np.eye(len(values))*1e-6,rhs)
    gains=weights/rms
    return (values*gains[:,None]).astype(np.float32),gains.tolist()


class ProcessingEngines:
    def __init__(self,config):
        self.config=config;self.root=Path(config['root']);self.options=config['audio_processing']
        import torch
        torch.set_num_threads(self.options['cpu_threads']);self.device=self.options['device']
        if self.device.startswith('cuda') and not torch.cuda.is_available():raise ValueError('音频处理配置使用 CUDA，但当前设备不可用；可显式改为 cpu')

    def source(self,key):
        p=Path(self.options[key]);return p if p.is_absolute() else self.root/p

    def load_weights(self,model,key,file):
        import torch
        source=json.loads((self.source(key)/'provenance.json').read_text(encoding='utf-8'))
        expected=next(item['sha256'] for item in source['files'] if item['file']==file)
        if sha256(self.source(key)/file)!=expected:raise ValueError('处理权重哈希不匹配：'+key)
        checkpoint=torch.load(self.source(key)/file,map_location='cpu',weights_only=True)
        state=checkpoint.get('model',checkpoint.get('state_dict',checkpoint))
        state={k.removeprefix('module.'):v for k,v in state.items()}
        model.load_state_dict(state,strict=True)
        return model.to(self.device).eval()

    def resample(self,y,source,target):
        if source==target:return y
        import librosa
        return librosa.resample(y,orig_sr=source,target_sr=target,axis=-1)

    def clearvoice(self):
        namespace('vf_clearvoice',self.root/'vendor/ClearerVoice-Studio/clearvoice/clearvoice')

    def separate(self,y,sr,progress,retain=False):
        import torch
        self.clearvoice()
        cls=importlib.import_module('vf_clearvoice.models.mossformer2_ss.mossformer2').MossFormer2_SS_16K
        args=SimpleNamespace(encoder_embedding_dim=512,mossformer_sequence_dim=512,num_mossformer_layer=24,encoder_kernel_size=16,num_spks=2)
        if not hasattr(self,'separator'):
            self.separator=self.load_weights(cls(args).model,'separation_dir','last_best_checkpoint.pt')
        model=self.separator
        mono=self.resample(y.mean(axis=0),sr,16000);rms=float(np.sqrt(np.mean(mono**2)))
        scale=max(rms,.01)
        def predict(chunk):
            with torch.inference_mode():
                outputs=model(torch.from_numpy(chunk/scale).to(self.device))
            return np.stack([o[0].float().cpu().numpy()*scale for o in outputs])
        output=overlap_add(mono,16000,self.options['speech_window_seconds'],predict,progress,True)
        output,gains=restore_source_scale(output,mono)
        self.stage_info=dict(scale_policy='least_squares_mixture_consistency',estimated_gains=gains)
        del model
        if not retain:self.close()
        return [('分离人声 A',output[0],16000),('分离人声 B',output[1],16000)]

    def separate_three(self,y,sr,progress):
        """Native three-source weights, 8 kHz output; never pretend resampling adds detail."""
        import torch
        path=self.source('three_separation_dir')
        manifest=json.loads((path/'provenance.json').read_text(encoding='utf-8'))
        for entry in manifest['files']:
            if sha256(path/entry['file'])!=entry['sha256']:raise ValueError('三人分离模型校验失败')
        if not hasattr(self,'separator_three'):
            from speechbrain.inference.separation import SepformerSeparation
            self.separator_three=SepformerSeparation.from_hparams(source=str(path),savedir=str(path),
                run_opts={'device':self.device},download_only=False)
        mono=self.resample(y.mean(axis=0),sr,8000)
        def predict(chunk):
            with torch.inference_mode():
                value=self.separator_three.separate_batch(torch.from_numpy(chunk).to(self.device))
            return value[0].float().cpu().numpy().T
        # One overlap piece is <= 8 seconds; preserve the three native outputs.
        output=predict(mono[None,:]);progress(1.)
        if output.shape!=(3,len(mono)) or not np.isfinite(output).all():raise ValueError('三人模型输出无效')
        output,_=restore_source_scale(output,mono)
        return [(f'三人分离 {i+1}',audio,8000) for i,audio in enumerate(output)]

    def close(self):
        for key in ('separator','separator_three'):
            if hasattr(self,key):delattr(self,key)
        self.release()

    def denoise(self,y,sr,progress):
        import torch
        self.clearvoice()
        cls=importlib.import_module('vf_clearvoice.models.mossformer2_se.mossformer2_se_wrapper').MossFormer2_SE_48K
        decoder=importlib.import_module('vf_clearvoice.utils.decode').decode_one_audio_mossformer2_se_48k
        args=SimpleNamespace(sampling_rate=48000,one_time_decode_length=20,decode_window=4,win_type='hamming',win_len=1920,win_inc=384,fft_len=1920,num_mels=60)
        model=self.load_weights(cls(args).model,'enhancement_dir','last_best_checkpoint.pt')
        mono=self.resample(y.mean(axis=0),sr,48000)
        def predict(chunk):
            if np.max(np.abs(chunk),initial=0)<1e-6:return np.zeros(chunk.shape[-1],dtype=np.float32)
            with torch.inference_mode():return decoder(model,self.device,chunk,args)
        output=overlap_add(mono,48000,4,predict,progress)[0]
        del model;self.release()
        return [('降噪人声',output,48000)]

    def remove_music(self,y,sr,progress):
        import torch
        # The MIT MSS implementation matches the author's released checkpoint, not the unlicensed demo tree.
        namespace('models',self.root/'vendor/Music-Source-Separation-Training/models')
        namespace('models.bs_roformer',self.root/'vendor/Music-Source-Separation-Training/models/bs_roformer')
        cls=importlib.import_module('models.bs_roformer.mel_band_roformer').MelBandRoformer
        specs=dict(dim=384,depth=6,stereo=True,num_stems=1,time_transformer_depth=1,freq_transformer_depth=1,
            num_bands=60,dim_head=64,heads=8,attn_dropout=0.,ff_dropout=0.,flash_attn=False,dim_freqs_in=1025,
            sample_rate=44100,stft_n_fft=2048,stft_hop_length=441,stft_win_length=2048,stft_normalized=False,mask_estimator_depth=2)
        model=self.load_weights(cls(**specs),'music_dir','MelBandRoformer.ckpt')
        stereo=self.resample(y,sr,44100)
        if len(stereo)==1:stereo=np.repeat(stereo,2,axis=0)
        stereo=stereo[:2]
        def predict(chunk):
            with torch.inference_mode():output=model(torch.from_numpy(chunk[None]).to(self.device))
            return output[0].float().cpu().numpy()
        vocals=overlap_add(stereo,44100,self.options['music_window_seconds'],predict,progress)
        background=stereo-vocals
        del model;self.release()
        return [('去音乐人声',vocals,44100),('分离出的背景音乐',background,44100)]

    def release(self):
        import torch
        gc.collect()
        if torch.cuda.is_available():torch.cuda.empty_cache()

    def process(self,request,folder,progress):
        y,sr=sf.read(request['input_path'],dtype='float32',always_2d=True);y=y.T
        current=[('输入',y,sr)];saved=[];steps=request['operations'];model_sources={}
        names={'remove_music':'music_dir','separate':'separation_dir','denoise':'enhancement_dir'}
        for index,step in enumerate(steps):
            next_audio=[]
            for branch,(label,pcm,rate) in enumerate(current):
                progress(5+85*(index+branch/max(1,len(current)))/len(steps),f'正在执行 {step} · {label}')
                self.stage_info={}
                outputs=getattr(self,step)(pcm if pcm.ndim==2 else pcm[None,:],rate,
                    lambda fraction:progress(5+85*(index+(branch+fraction)/len(current))/len(steps),f'正在执行 {step} · {label}'))
                for number,(name,audio,out_rate) in enumerate(outputs):
                    role='background' if name=='分离出的背景音乐' else 'speech'
                    path=Path(folder)/f'{index+1}-{branch+1}-{number+1}.wav'
                    peak=float(np.max(np.abs(audio),initial=0));gain=min(1.,.99/max(peak,1e-8))
                    write_wav(path,(audio*gain).T,out_rate) if audio.ndim==1 else self.write_multichannel(path,audio*gain,out_rate)
                    item=dict(label=(label+' → ' if label!='输入' else '')+name,file=str(path),sample_rate=out_rate,
                        duration=audio.shape[-1]/out_rate,channels=1 if audio.ndim==1 else len(audio),role=role,stage=step,
                        sha256=sha256(path),output_gain=gain,adapter_details=self.stage_info,final=index==len(steps)-1 or role=='background')
                    saved.append(item)
                    if role=='speech':next_audio.append((item['label'],audio*gain,out_rate))
            current=next_audio
            key=names[step];model_sources[key]=json.loads((self.source(key)/'provenance.json').read_text(encoding='utf-8'))
        return dict(outputs=saved,model_sources=model_sources,device=self.device,
            note='分离针对最多两路同时说话；A/B 是匿名输出，长静音后可能换位。去音乐/降噪可能产生残留或失真，请比较后选择。')

    def write_multichannel(self,path,pcm,rate):
        if not np.isfinite(pcm).all():raise ValueError('处理结果包含非有限采样')
        sf.write(path,pcm.T,rate,subtype='PCM_24')
