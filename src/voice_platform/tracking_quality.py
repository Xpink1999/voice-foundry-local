"""Source coverage and reference qualification; duration is never an identity proof."""
import math


def coverage(spans):
    intervals = sorted((float(s['source_start']), float(s['source_end'])) for s in spans)
    end = -math.inf
    seconds = 0.
    for first, last in intervals:
        if not math.isfinite(first + last) or first < 0 or last <= first:
            raise ValueError('片段来源时间映射无效')
        seconds += max(0., last - max(first, end))
        end = max(end, last)
    return seconds


def clip_stats(clip):
    # speech_spans are per-output VAD estimates, not VAD on the original mixture.
    speech = clip.get('speech_spans')
    return dict(file_seconds=clip['duration'],
                speech_seconds=coverage(speech) if speech is not None else None,
                source_seconds=coverage(clip['source_spans']),
                inserted_silence_seconds=max(0., clip['duration'] - coverage(clip['source_spans'])))


def reference_quality(clips, options, confirmed, rights):
    issues = []
    people = {c.get('speaker_id') for c in clips}
    if len(people) != 1 or None in people:
        issues.append('请选择同一人物的片段')
    if not confirmed:
        issues.append('请试听并确认所选片段属于同一人物')
    if not rights:
        issues.append('原录音尚未确认使用授权')
    if any(c.get('excluded') for c in clips):
        issues.append('所选片段包含已排除内容')
    # Source identity includes original recording hash at the caller boundary.
    # Overlapping alternative versions do not count twice or enter a reference twice.
    mapped = [s for c in clips for s in c['source_spans']]
    source_seconds = sum(coverage(c['source_spans']) for c in clips)
    unique_source_seconds = coverage(mapped)
    if source_seconds - unique_source_seconds > .02:
        issues.append('所选片段覆盖了重复的原始语音，请只保留一个版本')
    known = all(c.get('speech_spans') is not None for c in clips)
    speech = [s for c in clips for s in c.get('speech_spans', [])]
    unique_speech_seconds = coverage(speech) if known else None
    if not known:
        issues.append('片段缺少独立人声检测，请重新整理录音')
    elif unique_speech_seconds < options['reference_min_speech_seconds']:
        issues.append('有效人声不足，请增加清晰片段')
    file_seconds = sum(c['duration'] for c in clips)
    if file_seconds > options['reference_max_seconds']:
        issues.append('参考音频超过时长上限，请减少片段')
    return dict(state='blocked' if issues else 'needs_review', issues=issues,
                file_seconds=file_seconds, unique_source_seconds=unique_source_seconds,
                unique_speech_seconds=unique_speech_seconds, estimate=True,
                minimum_speech_seconds=options['reference_min_speech_seconds'],
                maximum_seconds=options['reference_max_seconds'],
                overlap_clips=sum(c.get('origin') == 'overlap' for c in clips))


def restore_timeline(clips, size, rate, read):
    """Restore compacted samples through every map entry, never from one start offset."""
    import numpy as np
    output = np.zeros(size, dtype=np.float32)
    occupied = np.zeros(size, dtype=bool)
    for clip in sorted(clips, key=lambda c: c.get('origin') != 'solo'):
        audio = read(clip)
        for span in clip['source_spans']:
            start, end = round(span['source_start'] * rate), round(span['source_end'] * rate)
            first = round(span.get('output_start', 0.) * rate)
            count = min(end - start, len(audio) - first, size - start)
            if count <= 0:
                continue
            free = ~occupied[start:start + count]
            output[start:start + count][free] = audio[first:first + count][free]
            occupied[start:start + count] = True
    return output
