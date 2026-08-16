"""
tts_engine.py
-------------
Robust Text-to-Speech Engine for Shorts Movie Maker.
Supports Style-BERT-VITS2 (local API) and edge-tts (cloud fallback),
and performs fail-safe audio ducking with FFmpeg.
"""

import os
import sys
import json
import asyncio
import subprocess
import requests

SBV2_DIR = "/Volumes/DTM/applications/Style-BERT-VITS2"
SBV2_PORTS = [5000, 5001, 7860, 8000]

EDGE_TTS_VOICES = {
    'ja-JP-NanamiNeural': 'Nanami (女性・自然で聴きやすい・推奨)',
    'ja-JP-KeitaNeural':  'Keita (男性・親しみやすい)',
    'ja-JP-NaokiNeural':  'Naoki (男性・落ち着いたアナウンス)',
    'ja-JP-AoiNeural':    'Aoi (女性・明るいトーン)',
    'ja-JP-DaichiNeural': 'Daichi (男性・力強い)'
}


def get_available_tts_models() -> dict:
    """
    Returns available Style-BERT-VITS2 models and edge-tts voices.
    """
    sbv2_models = []
    assets_dir = os.path.join(SBV2_DIR, "model_assets")
    if os.path.exists(assets_dir):
        for entry in os.listdir(assets_dir):
            p = os.path.join(assets_dir, entry)
            if os.path.isdir(p) and not entry.startswith('.'):
                sbv2_models.append(entry)

    if 'my_voice' in sbv2_models:
        sbv2_models.remove('my_voice')
        sbv2_models.insert(0, 'my_voice')

    return {
        'sbv2_available': len(sbv2_models) > 0,
        'sbv2_models': sbv2_models,
        'edge_voices': EDGE_TTS_VOICES
    }


def generate_edge_tts_audio(text: str, output_wav: str, voice: str = "ja-JP-NanamiNeural", rate: str = "+10%") -> str:
    """
    Generate speech audio using edge-tts (fast, natural, 100% reliable).
    """
    import edge_tts

    cleaned = text.replace('\n', ' ').strip()
    if not cleaned:
        return ""

    if not voice or voice == 'off' or voice not in EDGE_TTS_VOICES:
        voice = 'ja-JP-NanamiNeural'

    temp_mp3 = output_wav + ".mp3"

    async def _run():
        communicate = edge_tts.Communicate(cleaned, voice, rate=rate)
        await communicate.save(temp_mp3)

    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"[edge-tts error] {e}")
        # Secondary fallback with Nanami
        async def _run_fallback():
            communicate = edge_tts.Communicate(cleaned, 'ja-JP-NanamiNeural', rate='+10%')
            await communicate.save(temp_mp3)
        asyncio.run(_run_fallback())

    # Convert mp3 to 44.1kHz stereo wav
    cmd = [
        'ffmpeg', '-y', '-i', temp_mp3,
        '-ar', '44100', '-ac', '2',
        output_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    if os.path.exists(temp_mp3):
        try:
            os.remove(temp_mp3)
        except Exception:
            pass

    return output_wav


def _find_active_sbv2_port() -> int | None:
    """Check common Style-BERT-VITS2 ports"""
    for port in SBV2_PORTS:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/models/info", timeout=0.3)
            if r.status_code == 200:
                return port
        except Exception:
            pass
    return None


def generate_sbv2_audio(text: str, output_wav: str, model_name: str = "my_voice") -> str:
    """
    Generate speech audio via Style-BERT-VITS2 server if active, or instantly fallback to edge-tts.
    """
    cleaned = text.replace('\n', ' ').strip()
    if not cleaned:
        return ""

    port = _find_active_sbv2_port()
    if port:
        try:
            url = f"http://127.0.0.1:{port}/voice"
            params = {
                'text': cleaned,
                'model_name': model_name or 'my_voice',
                'length': 1.05
            }
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200 and len(res.content) > 100:
                with open(output_wav, 'wb') as f:
                    f.write(res.content)
                print(f"🎙️ [SBV2] Successfully generated audio using model: {model_name}")
                return output_wav
        except Exception as e:
            print(f"[SBV2 API Request failed] {e}")

    # If SBV2 server is not running, seamlessly generate with edge-tts without lag
    print("🎙️ [TTS] Style-BERT-VITS2 server offline -> Seamlessly using edge-tts (Nanami)")
    return generate_edge_tts_audio(cleaned, output_wav, voice="ja-JP-NanamiNeural")


def _has_audio_stream(video_path: str) -> bool:
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=codec_type',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    try:
        out = subprocess.check_output(cmd).decode('utf-8').strip()
        return 'audio' in out
    except Exception:
        return False


def overlay_voice_with_ducking(video_path: str,
                               voice_wav_path: str,
                               output_video_path: str,
                               duck_volume: float = 0.28,
                               voice_lead_in: float = 0.05) -> str:
    """
    Mix narration voiceover onto video with robust audio ducking.
    Handles video with or without existing audio gracefully.
    """
    if not os.path.exists(voice_wav_path) or os.path.getsize(voice_wav_path) < 100:
        import shutil
        shutil.copy2(video_path, output_video_path)
        return output_video_path

    # Check if input video has an audio stream
    has_audio = _has_audio_stream(video_path)

    # Get voiceover duration
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        voice_wav_path
    ]
    try:
        dur_res = subprocess.check_output(probe_cmd).decode('utf-8').strip()
        voice_dur = float(dur_res)
    except Exception:
        voice_dur = 2.5

    duck_end = voice_lead_in + voice_dur + 0.35

    if has_audio:
        # Mix original audio with ducking + voiceover
        filter_complex = (
            f"[1:a]adelay={int(voice_lead_in * 1000)}|{int(voice_lead_in * 1000)},volume=1.4[delayed_voice];"
            f"[0:a]volume=eval=frame:volume='if(lte(t,{duck_end}), {duck_volume} + (1.0 - {duck_volume}) * max(0, (t - {voice_dur + voice_lead_in}) / 0.35), 1.0)'[ducked_bgm];"
            f"[ducked_bgm][delayed_voice]amix=inputs=2:duration=first:dropout_transition=2[out_a]"
        )

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', voice_wav_path,
            '-filter_complex', filter_complex,
            '-map', '0:v:0',
            '-map', '[out_a]',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            output_video_path
        ]
    else:
        # No audio in original video -> directly use voiceover as audio track
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', voice_wav_path,
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            output_video_path
        ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode != 0:
        # Fallback simple amix
        simple_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', voice_wav_path,
            '-map', '0:v:0',
            '-map', '1:a:0?',
            '-c:v', 'copy',
            '-c:a', 'aac',
            output_video_path
        ]
        subprocess.run(simple_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    return output_video_path
