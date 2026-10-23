import gc
import json
import sys
from pathlib import Path

class VoxEngine:
    sample_rate = 48000
    def __init__(self, config):
        self.config = config
        self.model = None

    def capabilities(self):
        return dict(tts=True, voice_design=True, cloning=True, controllable_cloning=True, hifi_cloning=True, hifi_style_control=False, streaming=True,
                    style_control="approximate", speed_control="approximate", emotion_control="approximate",
                    word_timestamps=False, segment_timestamps=True,
                    parameters={"cfg_value": {"type": "number", "label": "引导强度", "default": 2.0, "min": 1, "max": 5, "step": 0.1},
                                "inference_timesteps": {"type": "integer", "label": "推理步数", "default": 10, "min": 4, "max": 50, "step": 1}},
                    languages=["ar","my","zh","da","nl","en","fi","fr","de","el","he","hi","id","it","ja","km","ko","lo","ms","no","pl","pt","ru","es","sw","sv","tl","th","tr","vi"],
                    notes="参考克隆/声音设计的语速、情绪、语气为自然语言近似引导；极致克隆（Hi-Fi）沿用参考演绎，不使用额外描述，避免被朗读。分段时间轴不等于词级对齐。")

    def identity(self):
        path = Path(self.config["model_dir"]) / "provenance.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(model="openbmb/VoxCPM2", revision="not-installed")

    def load(self):
        if self.model is None:
            root = Path(self.config['root'])
            if not (root/'vendor/VoxCPM/src/voxcpm').is_dir() or not (Path(self.config['model_dir'])/'model.safetensors').is_file():
                raise ValueError('VoxCPM2 is not installed. Run powershell -ExecutionPolicy Bypass -File scripts/install.ps1 from the installation directory. CoreOnly and SkipModels do not install model weights.')
            # Fixed official inference source; optional training/demo dependencies are not core dependencies.
            source = str(Path(self.config["root"]) / "vendor/VoxCPM/src")
            if source not in sys.path:
                sys.path.insert(0, source)
            from voxcpm import VoxCPM
            self.model = VoxCPM.from_pretrained(self.config["model_dir"], load_denoiser=False,
                                              optimize=False, device=self.config["device"], local_files_only=True)
            self.sample_rate = self.model.tts_model.sample_rate

    def unload(self):
        self.model = None
        gc.collect()
        torch = sys.modules.get('torch')
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def synthesize(self, request):
        self.load()
        control = request.get("style", "").strip()
        if request.get('clone_mode')=='hifi' and control:raise ValueError('Hi-Fi 不支持额外演绎描述；请创建新任务使用参考演绎，或切换参考克隆模式')
        options = request.get("engine_options", {})
        kwargs = dict(text=f"({control}){request['text']}" if control else request["text"],
                      seed=request["seed"], cfg_value=options.get("cfg_value", 2.0),
                      inference_timesteps=options.get("inference_timesteps", 10),
                      reference_wav_path=request.get("reference_path"), normalize=False,
                      denoise=False, retry_badcase=True, retry_badcase_max_times=1,
                      max_len=1024)
        if request.get('clone_mode')=='hifi':
            kwargs.update(prompt_wav_path=request['reference_path'],prompt_text=request['prompt_text'])
        if request.get("streaming"):
            yield from self.model.generate_streaming(**kwargs)
        else:
            yield self.model.generate(**kwargs)
