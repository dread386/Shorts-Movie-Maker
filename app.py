"""
app.py
------
Flask Web Application for Shorts Movie Maker.
Includes in-app Subtitle / SRT Editor and Instant Re-rendering.
"""

import os
import sys
import uuid
import time
import json
import zipfile
import threading
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

from core.audio_extractor import get_video_info, extract_audio
from core.whisper_sync import transcribe_full_audio
from core.highlight_detector import detect_highlights_gemini
from core.video_splitter import extract_vertical_clip
from core.vad_sync import get_clip_timeline, export_srt
from core.video_gen import render_subtitles_on_video, FONT_CATALOGUE


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

JOB_STORE = {}


@app.route('/')
def index():
    return render_template('index.html', fonts=FONT_CATALOGUE)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイル名が空です'}), 400

    job_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v']:
        return jsonify({'error': f'未対応の動画フォーマットです: {ext}'}), 400

    safe_name = secure_filename(file.filename) or f"upload_{job_id}{ext}"
    saved_filename = f"{job_id}_{safe_name}"
    video_path = os.path.join(UPLOAD_DIR, saved_filename)
    file.save(video_path)

    try:
        info = get_video_info(video_path)
    except Exception as e:
        info = {'duration': 60.0, 'width': 1920, 'height': 1080, 'fps': 30.0}

    return jsonify({
        'job_id': job_id,
        'filename': saved_filename,
        'video_info': info
    })


def _process_video_job(job_id: str, video_path: str, settings: dict):
    """
    Background worker that runs the full processing pipeline.
    """
    def update_progress(pct: float, phase: str, clips=None, error=None):
        JOB_STORE[job_id].update({
            'progress': round(pct, 3),
            'phase': phase,
            'clips': clips or JOB_STORE[job_id].get('clips', []),
            'error': error or JOB_STORE[job_id].get('error', '')
        })

    job_out_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_out_dir, exist_ok=True)

    try:
        # 1. Video Probe
        update_progress(0.05, "動画情報を解析中...")
        v_info = get_video_info(video_path)
        total_dur = v_info['duration']

        # 2. Extract Audio
        update_progress(0.12, "音声トラックを抽出中 (FFmpeg)...")
        wav_path = os.path.join(job_out_dir, f"audio_{job_id}.wav")
        extract_audio(video_path, wav_path)

        # 3. Whisper Speech-to-Text with anti-hallucination
        whisper_model = settings.get('whisper_model', 'base')
        language = settings.get('language', 'ja')

        def whisper_cb(sub_pct, msg):
            update_progress(0.15 + sub_pct * 0.35, msg)

        update_progress(0.18, f"AI文字起こし中 (Whisper {whisper_model})...")
        timeline = transcribe_full_audio(wav_path, model_size=whisper_model, language=language, progress_cb=whisper_cb)

        # 4. Highlight Detection (Gemini API / Rule-based)
        update_progress(0.55, "AIが動画のハイライトシーンを選定中...")
        max_clips = int(settings.get('max_clips', 4))
        target_dur = float(settings.get('target_duration', 15.0))
        api_key = settings.get('gemini_api_key', '').strip() or None
        custom_topic = settings.get('custom_topic', '').strip()

        highlight_clips = detect_highlights_gemini(
            timeline=timeline,
            total_duration=total_dur,
            api_key=api_key,
            max_clips=max_clips,
            target_duration=target_dur,
            custom_topic=custom_topic
        )

        update_progress(0.65, f"ハイライトシーン {len(highlight_clips)} 箇所を選定完了")

        # 5. Extract clips & burn subtitles
        crop_mode = settings.get('crop_mode', 'center_crop')
        show_subtitles = settings.get('show_subtitles', True)
        show_banner = settings.get('show_header_banner', True)

        generated_clips = []
        num_clips = len(highlight_clips)

        for i, clip in enumerate(highlight_clips):
            clip_idx = i + 1
            start_s = clip['start']
            end_s = clip['end']
            title = clip['title']
            
            clip_progress_base = 0.65 + (i / max(1, num_clips)) * 0.30
            clip_progress_step = 0.30 / max(1, num_clips)

            update_progress(clip_progress_base, f"ショート動画 #{clip_idx}/{num_clips} を切り出し中 ({title})...")

            # Cut 9:16 vertical raw video
            raw_clip_filename = f"clip_{clip_idx}_raw.mp4"
            raw_clip_path = os.path.join(job_out_dir, raw_clip_filename)
            extract_vertical_clip(video_path, start_s, end_s, raw_clip_path, crop_mode=crop_mode)

            # Get clip subtitle timeline
            clip_timeline = get_clip_timeline(timeline, start_s, end_s)

            # Save timeline JSON for in-app editing
            timeline_json_path = os.path.join(job_out_dir, f"clip_{clip_idx}_timeline.json")
            with open(timeline_json_path, 'w', encoding='utf-8') as f:
                json.dump(clip_timeline, f, ensure_ascii=False, indent=2)

            # Export initial SRT
            srt_filename = f"clip_{clip_idx}.srt"
            srt_path = os.path.join(job_out_dir, srt_filename)
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(export_srt(clip_timeline))

            # Final video path
            final_filename = f"shorts_{clip_idx}_{job_id}.mp4"
            final_path = os.path.join(job_out_dir, final_filename)

            # Render Subtitles & Banner
            if (show_subtitles and clip_timeline) or show_banner:
                def render_cb(p):
                    update_progress(clip_progress_base + p * clip_progress_step, f"テロップを焼き込み中 #{clip_idx} ({int(p*100)}%)...")

                render_subtitles_on_video(
                    input_video_path=raw_clip_path,
                    timeline=clip_timeline,
                    output_video_path=final_path,
                    clip_meta=clip,
                    settings=settings,
                    progress_cb=render_cb
                )
            else:
                import shutil
                shutil.copy2(raw_clip_path, final_path)

            generated_clips.append({
                'index': clip_idx,
                'title': title,
                'hook': clip.get('hook', ''),
                'summary': clip.get('summary', ''),
                'start': start_s,
                'end': end_s,
                'duration': round(end_s - start_s, 1),
                'video_url': f"/api/outputs/{job_id}/{final_filename}",
                'srt_url': f"/api/outputs/{job_id}/{srt_filename}",
                'filename': final_filename,
                'timeline': clip_timeline
            })

        # Complete
        JOB_STORE[job_id].update({
            'status': 'done',
            'progress': 1.0,
            'phase': 'すべてのショート動画が完成しました！🎉',
            'clips': generated_clips,
            'settings': settings
        })

    except Exception as e:
        print(f"[Job Error] {e}")
        JOB_STORE[job_id].update({
            'status': 'error',
            'error': str(e),
            'phase': f'エラーが発生しました: {e}'
        })


@app.route('/api/process', methods=['POST'])
def start_process():
    data = request.json or {}
    job_id = data.get('job_id')
    filename = data.get('filename')

    if not job_id or not filename:
        return jsonify({'error': 'job_id または filename が不足しています'}), 400

    video_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(video_path):
        return jsonify({'error': '指定された動画ファイルが見つかりません'}), 404

    JOB_STORE[job_id] = {
        'status': 'running',
        'progress': 0.01,
        'phase': '処理を開始しています...',
        'clips': [],
        'error': '',
        'created_at': time.time(),
        'filename': filename,
        'settings': data.get('settings', {})
    }

    thread = threading.Thread(
        target=_process_video_job,
        args=(job_id, video_path, data.get('settings', {})),
        daemon=True
    )
    thread.start()

    return jsonify({'status': 'started', 'job_id': job_id})


@app.route('/api/status/<job_id>')
def get_status(job_id):
    if job_id not in JOB_STORE:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(JOB_STORE[job_id])


@app.route('/api/clips/timeline/<job_id>/<int:clip_idx>')
def get_clip_timeline_endpoint(job_id, clip_idx):
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    timeline_file = os.path.join(job_dir, f"clip_{clip_idx}_timeline.json")
    if not os.path.exists(timeline_file):
        return jsonify({'error': 'Timeline not found'}), 404

    with open(timeline_file, 'r', encoding='utf-8') as f:
        timeline = json.load(f)

    return jsonify({
        'job_id': job_id,
        'clip_index': clip_idx,
        'timeline': timeline
    })


@app.route('/api/clips/re-render/<job_id>/<int:clip_idx>', methods=['POST'])
def re_render_clip(job_id, clip_idx):
    """
    Instantly re-burn edited subtitles and update SRT & video.
    """
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    raw_clip_path = os.path.join(job_dir, f"clip_{clip_idx}_raw.mp4")

    if not os.path.exists(raw_clip_path):
        return jsonify({'error': 'Raw clip not found'}), 404

    data = request.json or {}
    new_timeline = data.get('timeline', [])
    settings = data.get('settings') or (JOB_STORE.get(job_id, {}).get('settings', {}))

    # 1. Save new timeline JSON
    timeline_json_path = os.path.join(job_dir, f"clip_{clip_idx}_timeline.json")
    with open(timeline_json_path, 'w', encoding='utf-8') as f:
        json.dump(new_timeline, f, ensure_ascii=False, indent=2)

    # 2. Update SRT file
    srt_filename = f"clip_{clip_idx}.srt"
    srt_path = os.path.join(job_dir, srt_filename)
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write(export_srt(new_timeline))

    # 3. Re-render video
    final_filename = f"shorts_{clip_idx}_{job_id}.mp4"
    final_path = os.path.join(job_dir, final_filename)

    clip_meta = {'title': f"Clip #{clip_idx}", 'hook': settings.get('custom_banner_text', '')}
    if job_id in JOB_STORE and 'clips' in JOB_STORE[job_id]:
        for c in JOB_STORE[job_id]['clips']:
            if c['index'] == clip_idx:
                clip_meta = c
                break

    try:
        render_subtitles_on_video(
            input_video_path=raw_clip_path,
            timeline=new_timeline,
            output_video_path=final_path,
            clip_meta=clip_meta,
            settings=settings
        )
    except Exception as e:
        return jsonify({'error': f'Re-render failed: {e}'}), 500

    return jsonify({
        'status': 'success',
        'video_url': f"/api/outputs/{job_id}/{final_filename}?t={int(time.time())}",
        'srt_url': f"/api/outputs/{job_id}/{srt_filename}?t={int(time.time())}"
    })


@app.route('/api/outputs/<job_id>/<filename>')
def serve_output(job_id, filename):
    safe_fn = secure_filename(filename)
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    return send_from_directory(job_dir, safe_fn, as_attachment=False)


@app.route('/api/download_zip/<job_id>')
def download_zip(job_id):
    if job_id not in JOB_STORE or JOB_STORE[job_id].get('status') != 'done':
        return jsonify({'error': 'Job not ready or not found'}), 400

    job_dir = os.path.join(OUTPUT_DIR, job_id)
    zip_path = os.path.join(OUTPUT_DIR, f"Shorts_{job_id}.zip")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(job_dir):
            for file in files:
                if file.startswith('shorts_') or file.endswith('.srt'):
                    zipf.write(os.path.join(root, file), file)

    return send_file(zip_path, as_attachment=True, download_name=f"Shorts_{job_id}.zip")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5175))
    print(f"🎬 Shorts Movie Maker running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
