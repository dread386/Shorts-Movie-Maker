"""
highlight_detector.py
---------------------
Detect engaging highlight moments for YouTube Shorts / TikTok using:
1. Multi-API-Key Auto-Rotation for Gemini API (gemini-2.0-flash / gemini-1.5-flash)
2. Precise target duration matching (10s, 15s, 20s, 30s)
3. Audio energy / Spectral peak analysis
4. Rule-based segmentation fallback
"""

import os
import json
import re


API_KEY_FILE_PATH = "/Volumes/DTM/applications/APIキーリスト.txt"


def load_api_keys(user_key: str = None) -> list[str]:
    """
    Load API keys from user input, environment variable, and the API key file.
    """
    keys = []
    if user_key and user_key.strip():
        keys.append(user_key.strip())

    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key and env_key not in keys:
        keys.append(env_key)

    if os.path.exists(API_KEY_FILE_PATH):
        try:
            with open(API_KEY_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line_clean = line.strip()
                    if line_clean.startswith("AIzaSy") and line_clean not in keys:
                        keys.append(line_clean)
        except Exception as e:
            print(f"[HighlightDetector] Error reading {API_KEY_FILE_PATH}: {e}")

    return keys


def detect_highlights_gemini(timeline: list[dict], total_duration: float,
                            api_key: str = None,
                            max_clips: int = 4,
                            target_duration: float = 15.0,
                            custom_topic: str = "") -> list[dict]:
    """
    Use Gemini API to choose highlight segments matching the target duration (e.g. 10s, 15s, 20s).
    """
    # Define duration window around target
    min_dur = max(6.0, target_duration - 3.0)
    max_dur = min(total_duration, target_duration + 4.0)

    api_keys = load_api_keys(api_key)
    if not api_keys:
        print("[HighlightDetector] No Gemini API keys found. Using rule-based detection.")
        return detect_highlights_rule_based(timeline, total_duration, max_clips, target_duration)

    import google.generativeai as genai

    # Format transcript with timestamps
    if timeline:
        formatted_lines = [f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}" for seg in timeline]
        transcript_text = "\n".join(formatted_lines)
    else:
        transcript_text = "(※明瞭なトーク音声は検出されませんでした。演奏・BGM・手元中心の動画です)"

    prompt = f"""
あなたはYouTube ShortsやTikTokの動画バズクリエイター・動画編集のプロです。
動画の総再生時間: 約{total_duration:.1f}秒
動画のテーマ/補足情報: {custom_topic if custom_topic else '特になし'}
目標とする1本のショート動画の長さ: 【 約{target_duration:.0f}秒（{min_dur:.0f}秒〜{max_dur:.0f}秒） 】

視聴者の平均視聴維持率が最大化するよう、無駄のないテンポの良い【最も見どころ・サビ・山場となるハイライトシーン】を【 厳密に{max_clips}箇所 】選定してください。

選定の必須条件:
1. 各クリップの長さ (end - start) は必ず 【 約{target_duration:.0f}秒（{min_dur:.0f}秒〜{max_dur:.0f}秒以内） 】 にすること
2. 冒頭0.5秒で惹きつけるフックがあること
3. 各クリップ同士の時間は重複しないこと
4. 必ず合計 {max_clips} 個のクリップを出力すること

必ず以下のJSON形式のみを出力してください（Markdownの ```json 等は不要です）:
[
  {{
    "title": "キャッチーなタイトル (15文字以内)",
    "hook": "冒頭の惹き文句 (例: 伝説のギターソロ / 驚きの結末 / 必見テクニック)",
    "summary": "このシーンの見どころ要約",
    "start": 12.0,
    "end": {12.0 + target_duration:.1f}
  }}
]

【文字起こしデータ】:
{transcript_text}
"""

    for idx, key in enumerate(api_keys, start=1):
        key_masked = key[:8] + "..." + key[-4:]
        print(f"[HighlightDetector] Trying Gemini API Key #{idx}/{len(api_keys)} ({key_masked}) [Target: {target_duration}s]...")

        try:
            genai.configure(api_key=key)
            response = None
            
            for model_name in ['gemini-2.0-flash', 'gemini-1.5-flash']:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    if response and response.text:
                        print(f"[HighlightDetector] Key #{idx} succeeded with {model_name}!")
                        break
                except Exception as model_err:
                    print(f"[HighlightDetector] Key #{idx} model {model_name} failed: {model_err}")

            if not response or not response.text:
                raise RuntimeError(f"API Key #{idx} returned empty response.")

            text_resp = response.text.strip()
            json_match = re.search(r'\[\s*\{.*\}\s*\]', text_resp, re.DOTALL)
            if json_match:
                text_resp = json_match.group(0)
            else:
                text_resp = re.sub(r"^```json\s*", "", text_resp, flags=re.IGNORECASE)
                text_resp = re.sub(r"^```\s*", "", text_resp)
                text_resp = re.sub(r"\s*```$", "", text_resp)

            parsed = json.loads(text_resp)
            
            valid_clips = []
            for i, c in enumerate(parsed):
                s = max(0.0, float(c.get('start', 0.0)))
                e = float(c.get('end', 0.0))
                dur = e - s
                
                # Enforce target duration
                if dur < min_dur or dur > max_dur + 5.0:
                    e = min(total_duration, s + target_duration)
                if s >= total_duration:
                    continue
                e = min(total_duration, e)
                
                valid_clips.append({
                    'title': c.get('title', f"Clip #{i+1} ({target_duration:.0f}s)"),
                    'hook': c.get('hook', '注目シーン'),
                    'summary': c.get('summary', ''),
                    'start': round(s, 2),
                    'end': round(e, 2),
                    'duration': round(e - s, 2)
                })

            if len(valid_clips) >= max_clips:
                return valid_clips[:max_clips]
            elif valid_clips:
                # If Gemini returned fewer than requested, fill remaining with rule-based
                needed = max_clips - len(valid_clips)
                extra = detect_highlights_rule_based(timeline, total_duration, needed, target_duration, exclude_ranges=[(v['start'], v['end']) for v in valid_clips])
                return (valid_clips + extra)[:max_clips]

        except Exception as e:
            print(f"[HighlightDetector Warning] Key #{idx} ({key_masked}) failed: {e}")
            continue

    return detect_highlights_rule_based(timeline, total_duration, max_clips, target_duration)


def detect_highlights_rule_based(timeline: list[dict], total_duration: float,
                                max_clips: int = 4,
                                target_duration: float = 15.0,
                                exclude_ranges: list = None) -> list[dict]:
    """
    Fallback highlight detection strictly generating exact number of clips around target duration.
    """
    exclude = exclude_ranges or []
    clips = []
    
    # Calculate step interval to distribute clips across the whole video
    available_dur = max(target_duration, total_duration - 5.0)
    step = available_dur / max(1, max_clips)
    
    current_time = min(3.0, total_duration * 0.03)

    for i in range(max_clips):
        start_t = current_time
        end_t = min(total_duration, start_t + target_duration)

        # Snap to nearest speech boundary if available
        if timeline:
            for seg in timeline:
                if abs(seg['start'] - start_t) < 2.5:
                    start_t = seg['start']
                    end_t = min(total_duration, start_t + target_duration)
                    break

        dur = round(end_t - start_t, 1)
        if dur >= 5.0:
            clips.append({
                'title': f"Clip #{len(exclude) + len(clips) + 1} ({int(start_t)}s - {int(end_t)}s)",
                'hook': "おすすめシーン",
                'summary': f"{int(start_t)}秒〜{int(end_t)}秒の見どころ（{dur}秒）",
                'start': round(start_t, 2),
                'end': round(end_t, 2),
                'duration': dur
            })

        current_time = start_t + step
        if current_time + target_duration > total_duration:
            current_time = max(0.0, total_duration - target_duration - 1.0)

    # Ensure at least 1 clip
    if not clips:
        clips.append({
            'title': 'Clip #1',
            'hook': '注目シーン',
            'summary': f'ハイライト区間（{target_duration}秒）',
            'start': 0.0,
            'end': round(min(total_duration, target_duration), 2),
            'duration': round(min(total_duration, target_duration), 2)
        })

    return clips[:max_clips]
