"""
tts_engine.py
-------------
Handles text-to-speech generation using Style-BERT-VITS2 (local) or edge-tts (cloud),
and performs smart audio ducking with FFmpeg to mix voiceover over video.
"""

import os
import sys
import json
import asyncio
import subprocess
import requests

SBV2_DIR = "/Volumes/DTM/applications/Style-BERT-VITS2"
SBV2_PYTHON = os.path.join(SBV2_DIR, "venv", "bin", "python")
SBV2_DEFAULT_PORT = 5000

EDGE_TTS_VOICES = {
    'ja-JP-NanamiNeural': 'Nanami (女性・自然で聴きやすい)',
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

    # Put my_voice first if present
    if 'my_voice' in sbv2_models:
        sbv2_models.remove('my_voice')
        sbv2_models.insert(0, 'my_voice')

    return {
        'sbv2_available': os.path.exists(SBV2_PYTHON),
        'sbv2_models': sbv2_models,
        'edge_voices': EDGE_TTS_VOICES
    }


def generate_edge_tts_audio(text: str, output_wav: str, voice: str = "ja-JP-NanamiNeural", rate: str = "+10%") -> str:
    """
    Generate speech audio using edge-tts (fast, natural, free).
    """
    import edge_tts

    # Clean text (remove newlines and excess punctuation)
    cleaned = text.replace('\n', ' ').strip()
    if not cleaned:
        return ""

    temp_mp3 = output_wav + ".mp3"

    async def _run():
        communicate = edge_tts.Communicate(cleaned, voice, rate=rate)
        await communicate.save(temp_mp3)

    asyncio.run(_run())

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


def generate_sbv2_audio(text: str, output_wav: str, model_name: str = "my_voice", port: int = SBV2_DEFAULT_PORT) -> str:
    """
    Generate speech audio via Style-BERT-VITS2 server or direct python runner.
    """
    cleaned = text.replace('\n', ' ').strip()
    if not cleaned:
        return ""

    # 1. Try hitting active FastAPI server
    try:
        url = f"http://127.0.0.1:{port}/voice"
        params = {
            'text': cleaned,
            'model_name': model_name,
            'length': 1.05 # slightly faster for short video punch
        }
        res = requests.get(url, params=params, timeout=4)
        if res.status_code == 200 and len(res.content) > 100:
            with open(output_wav, 'wb') as f:
                f.write(res.content)
            return output_wav
    except Exception:
        pass

    # 2. Direct Python execution using SBV2 venv if available
    script_path = os.path.join(os.path.dirname(__file__), "_sbv2_direct_infer.py")
    _ensure_sbv2_direct_script(script_path)

    if os.path.exists(SBV2_PYTHON) and os.path.exists(script_path):
        try:
            cmd = [
                SBV2_PYTHON, script_path,
                "--text", cleaned,
                "--model_name", model_name,
                "--out", output_wav
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0 and os.path.exists(output_wav) and os.path.getsize(output_wav) > 100:
                return output_wav
        except Exception as e:
            print(f"[SBV2 Direct Error] {e}")

    # 3. Fallback to edge-tts if SBV2 is not responsive
    print("[TTS] Falling back to edge-tts for speech synthesis...")
    return generate_edge_tts_audio(cleaned, output_wav)


def _ensure_sbv2_direct_script(target_path: str):
    """
    Create a standalone direct inference helper that runs inside Style-BERT-VITS2 directory.
    """
    if os.path.exists(target_path):
        return

    content = '''import sys
import os
import argparse
from pathlib import Path

# Add Style-BERT-VITS2 root to sys.path
SBV2_ROOT = "/Volumes/DTM/applications/Style-BERT-VITS2"
sys.path.insert(0, SBV2_ROOT)
os.chdir(SBV2_ROOT)

import torch
from scipy.io import wavfile
from style_bert_vits2.tts_model import TTSModel, TTSModelHolder
from style_bert_vits2.nlp.japanese import pyopenjtalk_worker as pyopenjtalk
from style_bert_vits2.nlp.japanese.user_dict import update_dict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--model_name", default="my_voice")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    model_dir = Path(SBV2_ROOT) / "model_assets" / args.model_name

    # Find .pth file
    pth_files = list(model_dir.glob("*.pth")) or list(model_dir.glob("*.safetensors"))
    if not pth_files:
        sys.exit(1)

    pyopenjtalk.initialize_worker()
    update_dict()

    model = TTSModel(
        model_path=pth_files[0],
        config_path=model_dir / "config.json",
        style_vec_path=model_dir / "style_vectors.npy",
        device=device
    )
    model.load()

    sr, audio = model.infer(text=args.text, length=1.05)
    wavfile.write(args.out, sr, audio)

if __name__ == "__main__":
    main()
'''
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass


def overlay_voice_with_ducking(video_path: str,
                               voice_wav_path: str,
                               output_video_path: str,
                               duck_volume: float = 0.28,
                               voice_lead_in: float = 0.05) -> str:
    """
    Mix narration voiceover onto video with smart audio ducking using FFmpeg.
    The original video's audio is lowered during the voiceover and smoothly restored after.
    """
    if not os.path.exists(voice_wav_path) or os.path.getsize(voice_wav_path) < 100:
        import shutil
        shutil.copy2(video_path, output_video_path)
        return output_video_path

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

    # Filter graph:
    # 1. Delay voice by voice_lead_in
    # 2. Lower original audio from 0 to duck_end, then smoothly return to 1.0
    # 3. amix both streams
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
        '-shortest',
        output_video_path
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode != 0:
        # Fallback if complex filter fails: simple amix
        simple_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', voice_wav_path,
            '-filter_complex', '[0:a]volume=0.8[a0];[1:a]volume=1.3[a1];[a0][a1]amix=inputs=2:duration=first[out_a]',
            '-map', '0:v:0',
            '-map', '[out_a]',
            '-c:v', 'copy',
            '-c:a', 'aac',
            output_video_path
        ]
        subprocess.run(simple_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    return output_video_path
