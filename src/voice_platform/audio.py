import hashlib
import re
import shutil
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def split_text(text, limit):
    """Preserve every non-whitespace character and punctuation, bound each segment."""
    pieces = re.split(r"(?<=[。！？.!?；;\n])", text)
    out, current = [], ""
    for piece in pieces:
        while len(piece) > limit:
            if current.strip():
                out.append(current.strip())
                current = ""
            pivot = max(piece.rfind(c, 0, limit + 1) for c in ("，", ",", " ", "、"))
            pivot = pivot + 1 if pivot >= limit // 2 else limit
            out.append(piece[:pivot].strip())
            piece = piece[pivot:]
        if len(current) + len(piece) > limit and current.strip():
            out.append(current.strip())
            current = ""
        current += piece
    if current.strip():
        out.append(current.strip())
    return out

def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")[:100]
    if value.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *[f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)]}:
        value = "_" + value
    return value or "audio"

def write_wav(path, pcm, sample_rate):
    pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
    if not len(pcm) or not np.isfinite(pcm).all():
        raise ValueError("模型返回空音频或无效采样")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".part.wav")
    sf.write(temp, pcm, sample_rate, subtype="PCM_24")
    temp.replace(path)

def srt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"

def write_srt(path, segments):
    text = "\n\n".join(f"{i+1}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}" for i, s in enumerate(segments))
    Path(path).write_text(text + "\n", encoding="utf-8")

def convert_audio(source, target, options, ffmpeg):
    if options["format"] == "wav" and options["sample_rate"] == sf.info(source).samplerate and options["channels"] == sf.info(source).channels and not options["normalize"] and not options["trim_silence"]:
        shutil.copy2(source, target)
        return
    filters = []
    if options["trim_silence"]:
        filters.append("silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse")
    if options["normalize"]:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    if filters:
        command += ["-af", ",".join(filters)]
    codec = dict(wav="pcm_s24le", mp3="libmp3lame", flac="flac", ogg="libvorbis")[options["format"]]
    command += ["-ar", str(options["sample_rate"]), "-ac", str(options["channels"]), "-c:a", codec, str(target)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=300)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise ValueError("音频编码工具不可用或处理超时，请检查 FFmpeg 配置") from error
    if result.returncode:
        raise ValueError("音频后处理失败: " + result.stderr.decode("utf-8", errors="replace")[-2000:])
