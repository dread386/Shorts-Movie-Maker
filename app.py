"""
app.py
------
Flask Web Application for Shorts Movie Maker.
Includes in-app Subtitle / SRT & Banner Editor, Voiceover (Style-BERT-VITS2 & edge-tts),
Instant Re-rendering, and High-CTR 9:16 Thumbnail Generation.
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
from core.video_splitter import extract_vertical_clip, GRID_CELLS, GRID_LAYOUT_SLOTS
from core.vad_sync import get_clip_timeline, export_srt
from core.video_gen import render_subtitles_on_video, generate_clip_thumbnail, FONT_CATALOGUE
from core.tts_engine import get_available_tts_models, generate_voiceover, overlay_voice_with_ducking, check_sbv2_status


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

JOB_STORE = {}


@app.route('/')
def index():
    tts_info = get_available_tts_models()
    return render_template(
        'index.html',
        fonts=FONT_CATALOGUE,
        tts_info=tts_info,
        grid_cells=GRID_CELLS,
        grid_layouts=GRID_LAYOUT_SLOTS
    )



@app.route('/api/tts_status')
def get_tts_status():
    return jsonify(get_available_tts_models())



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
    Background worker that runs the full processing pipeline:
    Probe -> Extract Audio -> Whisper -> Gemini Highlights -> Vertical Cut -> TTS Hook & Ducking -> Burn Subs -> Thumbnails
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
        update_progress(0.10, "音声トラックを抽出中 (FFmpeg)...")
        wav_path = os.path.join(job_out_dir, f"audio_{job_id}.wav")
        extract_audio(video_path, wav_path)

        # 3. Whisper Speech-to-Text with anti-hallucination
        whisper_model = settings.get('whisper_model', 'base')
        language = settings.get('language', 'ja')

        def whisper_cb(sub_pct, msg):
            update_progress(0.12 + sub_pct * 0.38, msg)

        update_progress(0.15, f"AI文字起こし中 (Whisper {whisper_model})...")
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

        # 5. Extract clips, synthesize TTS, burn subtitles, & generate thumbnails
        crop_mode = settings.get('crop_mode', 'blur_pad')
        show_subtitles = settings.get('show_subtitles', True)
        show_banner = settings.get('show_header_banner', True)
        tts_enabled = settings.get('tts_enabled', True)
        tts_engine_choice = settings.get('tts_engine', 'sbv2') # 'sbv2' | 'edge_tts' | 'off'
        tts_model = settings.get('tts_model', 'my_voice')

        generated_clips = []
        num_clips = len(highlight_clips)

        for i, clip in enumerate(highlight_clips):
            clip_idx = i + 1
            start_s = clip['start']
            end_s = clip['end']
            title = clip['title']
            hook = clip.get('hook') or title
            banner_text = settings.get('custom_banner_text', '').strip() or hook
            
            clip_progress_base = 0.65 + (i / max(1, num_clips)) * 0.30
            clip_progress_step = 0.30 / max(1, num_clips)

            update_progress(clip_progress_base, f"ショート動画 #{clip_idx}/{num_clips} を切り出し中 ({title})...")

            # Cut 9:16 vertical raw video
            raw_clip_filename = f"clip_{clip_idx}_raw.mp4"
            raw_clip_path = os.path.join(job_out_dir, raw_clip_filename)
            grid_layout = settings.get('grid_layout', 'split_2_vertical')
            grid_slots = settings.get('grid_slots', ['A', 'F'])
            extract_vertical_clip(
                video_path, start_s, end_s, raw_clip_path,
                crop_mode=crop_mode,
                grid_layout=grid_layout,
                grid_slots=grid_slots
            )


            # Optional: Synthesize Voiceover Hook & Ducking
            effective_video_path = raw_clip_path
            if tts_enabled and tts_engine_choice != 'off' and banner_text:
                update_progress(clip_progress_base + clip_progress_step * 0.2, f"ナレーション音声を合成中 #{clip_idx} ({tts_model or tts_engine_choice})...")
                voice_wav_path = os.path.join(job_out_dir, f"voice_{clip_idx}.wav")
                try:
                    generate_voiceover(banner_text, voice_wav_path, tts_engine=tts_engine_choice, tts_model=tts_model)
                    if os.path.exists(voice_wav_path) and os.path.getsize(voice_wav_path) > 100:
                        ducked_video_path = os.path.join(job_out_dir, f"clip_{clip_idx}_ducked.mp4")
                        overlay_voice_with_ducking(raw_clip_path, voice_wav_path, ducked_video_path)
                        effective_video_path = ducked_video_path
                except Exception as e:
                    print(f"[TTS Synthesis Error] {e}")


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
            def render_cb(p):
                update_progress(clip_progress_base + clip_progress_step * (0.4 + p * 0.5), f"テロップを焼き込み中 #{clip_idx} ({int(p*100)}%)...")

            clip_meta_for_render = {**clip, 'hook': banner_text}
            render_subtitles_on_video(
                input_video_path=effective_video_path,
                timeline=clip_timeline,
                output_video_path=final_path,
                clip_meta=clip_meta_for_render,
                settings=settings,
                progress_cb=render_cb
            )

            # Generate High-CTR 9:16 Thumbnail Image
            thumb_filename = f"thumb_{clip_idx}_{job_id}.png"
            thumb_path = os.path.join(job_out_dir, thumb_filename)
            first_sub = clip_timeline[0]['text'] if clip_timeline else ""
            generate_clip_thumbnail(
                video_path=final_path,
                output_png_path=thumb_path,
                banner_text=banner_text,
                subtitle_text=first_sub,
                settings=settings,
                capture_sec=0.5
            )

            generated_clips.append({
                'index': clip_idx,
                'title': title,
                'hook': hook,
                'banner_text': banner_text,
                'summary': clip.get('summary', ''),
                'start': start_s,
                'end': end_s,
                'duration': round(end_s - start_s, 1),
                'video_url': f"/api/outputs/{job_id}/{final_filename}",
                'thumbnail_url': f"/api/outputs/{job_id}/{thumb_filename}",
                'srt_url': f"/api/outputs/{job_id}/{srt_filename}",
                'filename': final_filename,
                'thumb_filename': thumb_filename,
                'timeline': clip_timeline
            })

        # Complete
        JOB_STORE[job_id].update({
            'status': 'done',
            'progress': 1.0,
            'phase': 'すべてのショート動画＆サムネイルが完成しました！🎉',
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

    banner_text = ""
    if job_id in JOB_STORE and 'clips' in JOB_STORE[job_id]:
        for c in JOB_STORE[job_id]['clips']:
            if c['index'] == clip_idx:
                banner_text = c.get('banner_text') or c.get('hook') or ""
                break

    return jsonify({
        'job_id': job_id,
        'clip_index': clip_idx,
        'banner_text': banner_text,
        'timeline': timeline
    })


@app.route('/api/clips/re-render/<job_id>/<int:clip_idx>', methods=['POST'])
def re_render_clip(job_id, clip_idx):
    """
    Instantly re-burn edited subtitles, updated banner text, voiceover, and re-generate thumbnail.
    """
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    raw_clip_path = os.path.join(job_dir, f"clip_{clip_idx}_raw.mp4")

    if not os.path.exists(raw_clip_path):
        return jsonify({'error': 'Raw clip not found'}), 404

    data = request.json or {}
    new_timeline = data.get('timeline', [])
    new_banner_text = data.get('banner_text', '').strip()
    regenerate_tts = data.get('regenerate_tts', False)
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

    # 3. Optional: Regenerate Voiceover if requested
    effective_video_path = raw_clip_path
    tts_engine_choice = data.get('tts_engine') or settings.get('tts_engine', 'sbv2')
    tts_model = data.get('tts_model') or settings.get('tts_model', 'my_voice')
    banner_font_size = int(data.get('banner_font_size') or settings.get('banner_font_size', 50))

    if regenerate_tts and new_banner_text and tts_engine_choice != 'off':
        voice_wav_path = os.path.join(job_dir, f"voice_{clip_idx}.wav")
        try:
            generate_voiceover(new_banner_text, voice_wav_path, tts_engine=tts_engine_choice, tts_model=tts_model)
            if os.path.exists(voice_wav_path) and os.path.getsize(voice_wav_path) > 100:
                ducked_video_path = os.path.join(job_dir, f"clip_{clip_idx}_ducked.mp4")
                overlay_voice_with_ducking(raw_clip_path, voice_wav_path, ducked_video_path)
                effective_video_path = ducked_video_path
        except Exception as e:
            print(f"[Re-render TTS Error] {e}")
    else:
        # Check if existing ducked video exists
        ducked_video_path = os.path.join(job_dir, f"clip_{clip_idx}_ducked.mp4")
        if os.path.exists(ducked_video_path):
            effective_video_path = ducked_video_path

    # 4. Re-render video
    final_filename = f"shorts_{clip_idx}_{job_id}.mp4"
    final_path = os.path.join(job_dir, final_filename)

    merged_settings = {
        **settings,
        'custom_banner_text': new_banner_text,
        'banner_font_size': banner_font_size,
        'tts_engine': tts_engine_choice,
        'tts_model': tts_model
    }

    clip_meta = {'title': f"Clip #{clip_idx}", 'hook': new_banner_text}
    if job_id in JOB_STORE and 'clips' in JOB_STORE[job_id]:
        for c in JOB_STORE[job_id]['clips']:
            if c['index'] == clip_idx:
                c['banner_text'] = new_banner_text
                clip_meta = c
                break

    try:
        render_subtitles_on_video(
            input_video_path=effective_video_path,
            timeline=new_timeline,
            output_video_path=final_path,
            clip_meta=clip_meta,
            settings=merged_settings
        )

        # 5. Re-generate Thumbnail
        thumb_filename = f"thumb_{clip_idx}_{job_id}.png"
        thumb_path = os.path.join(job_dir, thumb_filename)
        first_sub = new_timeline[0]['text'] if new_timeline else ""
        generate_clip_thumbnail(
            video_path=final_path,
            output_png_path=thumb_path,
            banner_text=new_banner_text,
            subtitle_text=first_sub,
            settings=merged_settings,
            capture_sec=0.5
        )


    except Exception as e:
        return jsonify({'error': f'Re-render failed: {e}'}), 500

    ts = int(time.time())
    return jsonify({
        'status': 'success',
        'video_url': f"/api/outputs/{job_id}/{final_filename}?t={ts}",
        'thumbnail_url': f"/api/outputs/{job_id}/{thumb_filename}?t={ts}",
        'srt_url': f"/api/outputs/{job_id}/{srt_filename}?t={ts}"
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
                if file.startswith('shorts_') or file.endswith('.srt') or file.startswith('thumb_'):
                    zipf.write(os.path.join(root, file), file)

    return send_file(zip_path, as_attachment=True, download_name=f"Shorts_{job_id}.zip")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5175))
    print(f"🎬 Shorts Movie Maker running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
