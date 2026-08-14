"""
whisper_sync.py
---------------
Transcribe full audio file with Whisper into timestamped segments.
Includes strict anti-hallucination filters (preventing fake '作詞・作曲' on instrumental sections).
"""

import os
import re
import whisper

# Typical Whisper hallucination phrases on music / instrumental / silent parts
HALLUCINATION_PATTERNS = [
    r'作詞[・\s]*作曲',
    r'作詞',
    r'作曲',
    r'ご視聴ありがとう',
    r'視聴ありがとう',
    r'チャンネル登録',
    r'高評価',
    r'字幕[：:]',
    r'Subtitles? by',
    r'Thank you for watching',
    r'Please subscribe',
    r'Like and subscribe',
    r'MBC',
    r'KBS',
    r'SBS',
]


def clean_hallucinations(text: str) -> str:
    """Filter out known hallucination phrases."""
    t = text.strip()
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            # If the line contains typical hallucination keywords, drop it completely or clean it
            t = re.sub(r'^.*' + pat + r'.*$', '', t, flags=re.IGNORECASE).strip()
    return t


def transcribe_full_audio(audio_path: str, model_size: str = 'base', language: str = 'ja',
                           progress_cb=None) -> list[dict]:
    """
    Transcribe an audio file and return a structured timeline of clean segments:
    [
        {'start': 0.0, 'end': 3.45, 'text': 'こんにちは、今回は...'},
        ...
    ]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if progress_cb:
        progress_cb(0.1, f"Whisper モデル '{model_size}' をロード中...")

    model = whisper.load_model(model_size)

    if progress_cb:
        progress_cb(0.3, "音声を文字起こし中 (Whisper AI)...")

    # Use strict anti-hallucination parameters
    result = model.transcribe(
        audio_path,
        language=language,
        verbose=False,
        fp16=False,
        no_speech_threshold=0.6,          # Reject silent/music segments
        logprob_threshold=-1.0,           # Filter low-confidence outputs
        condition_on_previous_text=False  # Prevent repeating hallucination loops
    )

    raw_segments = result.get('segments', [])
    timeline = []

    for seg in raw_segments:
        # Check non-speech probability
        no_speech = seg.get('no_speech_prob', 0.0)
        if no_speech > 0.65:
            continue

        raw_text = seg.get('text', '').strip()
        cleaned_text = clean_hallucinations(raw_text)

        if not cleaned_text or len(cleaned_text) <= 1:
            continue

        timeline.append({
            'start': round(float(seg['start']), 2),
            'end': round(float(seg['end']), 2),
            'text': cleaned_text
        })

    if progress_cb:
        progress_cb(0.6, f"文字起こし完了: {len(timeline)} セグメント検出 (ノイズ・幻覚除去済み)")

    return timeline
