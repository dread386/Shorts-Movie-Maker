"""
vad_sync.py
------------
Subtitle timeline processing, SRT formatting, and clip-scoped timeline extraction.
"""

def export_srt(timeline: list[dict], offset: float = 0.0) -> str:
    """
    Export timeline to standard SubRip Subtitle (.srt) format.
    offset: seconds to subtract from start/end times (useful for trimmed clips).
    """
    def fmt_time(seconds: float) -> str:
        s = max(0.0, seconds - offset)
        ms = int(round((s - int(s)) * 1000))
        total_sec = int(s)
        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

    lines = []
    idx = 1
    for entry in timeline:
        start_t = entry['start'] - offset
        end_t = entry['end'] - offset
        if end_t <= 0:
            continue
        start_t = max(0.0, start_t)
        if end_t <= start_t:
            end_t = start_t + 1.0

        lines.append(str(idx))
        lines.append(f"{fmt_time(entry['start'])} --> {fmt_time(entry['end'])}")
        lines.append(entry['text'])
        lines.append("")
        idx += 1

    return "\n".join(lines)


def get_clip_timeline(full_timeline: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """
    Extract subtitle segments that overlap with the given [clip_start, clip_end] interval,
    and shift their timestamps so that clip_start becomes 0.0.
    """
    clip_timeline = []

    for item in full_timeline:
        s = item['start']
        e = item['end']
        text = item['text']

        # Check overlap
        if e > clip_start and s < clip_end:
            adjusted_start = max(0.0, s - clip_start)
            adjusted_end = min(clip_end - clip_start, e - clip_start)

            if adjusted_end > adjusted_start:
                clip_timeline.append({
                    'start': round(adjusted_start, 2),
                    'end': round(adjusted_end, 2),
                    'text': text
                })

    return clip_timeline
