"""
audio_extractor.py
------------------
Extract audio from video files and get media metadata using FFmpeg/FFprobe.
"""

import os
import json
import subprocess


def get_video_info(video_path: str) -> dict:
    """
    Retrieve video metadata (duration, width, height, fps, etc.) via ffprobe.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        data = json.loads(res.stdout)
    except Exception as e:
        # Fallback using ffmpeg directly if ffprobe output parsing fails
        return _fallback_get_video_info(video_path)

    duration = 0.0
    if 'format' in data and 'duration' in data['format']:
        duration = float(data['format']['duration'])

    width = 1920
    height = 1080
    fps = 30.0

    for stream in data.get('streams', []):
        if stream.get('codec_type') == 'video':
            width = int(stream.get('width', width))
            height = int(stream.get('height', height))
            r_frame_rate = stream.get('r_frame_rate', '30/1')
            if '/' in r_frame_rate:
                num, den = r_frame_rate.split('/')
                if float(den) > 0:
                    fps = float(num) / float(den)
            break

    return {
        'duration': duration,
        'width': width,
        'height': height,
        'fps': round(fps, 2)
    }


def _fallback_get_video_info(video_path: str) -> dict:
    """Fallback probe via ffmpeg -i"""
    cmd = ['ffmpeg', '-i', video_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out = proc.stderr

    duration = 60.0
    import re
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if dur_match:
        h, m, s = dur_match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    return {
        'duration': duration,
        'width': 1920,
        'height': 1080,
        'fps': 30.0
    }


def extract_audio(video_path: str, output_wav_path: str, sample_rate: int = 16000) -> str:
    """
    Extract 16kHz mono WAV audio from video file for Whisper and audio analysis.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)

    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', str(sample_rate),
        '-ac', '1',
        output_wav_path
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    return output_wav_path
