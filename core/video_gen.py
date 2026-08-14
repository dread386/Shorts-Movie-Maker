"""
video_gen.py
------------
Burns rendered animated / outlined subtitles and optional header banners
onto vertical video clips (1080x1920) using Pillow and FFmpeg frame piping.
"""

import os
import re
import subprocess
import threading
from PIL import Image, ImageDraw, ImageFont

from core.text_splitter import auto_split_timeline


FONT_CATALOGUE = {
    'ja_kaku': {
        'label': 'Apple SD Gothic Neo (角ゴシック / Japanese)',
        'path':  '/System/Library/Fonts/AppleSDGothicNeo.ttc',
        'index': 6,
    },
    'ja_maru': {
        'label': 'ヒラギノ丸ゴシック (Hiragino Maru Gothic / Japanese)',
        'path':  '/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc',
        'index': 1,
    },
    'ja_heiti': {
        'label': 'STHeiti (明朝・ゴシック黒体 / Japanese)',
        'path':  '/System/Library/Fonts/STHeiti Medium.ttc',
        'index': 0,
    },
    'universal': {
        'label': 'Arial Unicode (Universal / EN + JA)',
        'path':  '/Library/Fonts/Arial Unicode.ttf',
        'index': 0,
    }
}

DEFAULT_SETTINGS = {
    'width': 1080,
    'height': 1920,
    'fps': 30,
    'font_key': 'ja_kaku',
    'font_size': 66,
    'font_weight': 2,
    'text_color': '#FFFFFF',
    'outline_color': '#000000',
    'outline_width': 6,
    'position': 'bottom', # 'top' | 'center' | 'bottom'
    'bottom_margin': 340, # Above typical TikTok/Shorts bottom UI
    'top_margin': 200,
    'fade_in': 0.1,
    'fade_out': 0.1,
    'display_mode': '1_line',
    'max_chars_per_line': 12,
    'show_subtitles': True,
    'show_header_banner': True,
    'custom_banner_text': ''
}


def _parse_color(hex_str: str) -> tuple:
    """'#RRGGBB' -> (R, G, B)"""
    h = hex_str.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _load_font(font_key: str, font_size: int) -> ImageFont.FreeTypeFont:
    cat = FONT_CATALOGUE.get(font_key, FONT_CATALOGUE['ja_kaku'])
    if os.path.exists(cat['path']):
        try:
            return ImageFont.truetype(cat['path'], font_size, index=cat.get('index', 0))
        except Exception:
            pass

    fallback_fonts = [
        ('/System/Library/Fonts/AppleSDGothicNeo.ttc', 6),
        ('/System/Library/Fonts/STHeiti Medium.ttc', 0),
        ('/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc', 1)
    ]
    for path, idx in fallback_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size, index=idx)
            except Exception:
                continue

    return ImageFont.load_default()


def _draw_outlined_text(draw, text, font, cx, y, text_rgba, outline_rgba, outline_w, font_weight=1):
    lines = text.split('\n')
    curr_y = y
    eff_outline = outline_w + font_weight
    line_spacing = int(font.size * 0.2)

    for line in lines:
        if not line:
            continue
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = cx - tw // 2

        # Draw thick outline
        for dx in range(-eff_outline, eff_outline + 1):
            for dy in range(-eff_outline, eff_outline + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, curr_y + dy), line, font=font, fill=outline_rgba)

        # Draw text body with bold offset
        for w_offset in range(font_weight + 1):
            draw.text((x + w_offset, curr_y), line, font=font, fill=text_rgba)

        curr_y += th + line_spacing


def render_subtitles_on_video(input_video_path: str,
                             timeline: list[dict],
                             output_video_path: str,
                             clip_meta: dict = None,
                             settings: dict = None,
                             progress_cb=None):
    """
    Burn subtitles and header badge on top of a 9:16 vertical video clip.
    """
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    W, H, FPS = s['width'], s['height'], s['fps']
    show_subtitles = s.get('show_subtitles', True)
    show_banner = s.get('show_header_banner', True)
    custom_banner = s.get('custom_banner_text', '').strip()

    # If neither subtitles nor banner is needed, copy original
    if not show_subtitles and not show_banner:
        import shutil
        shutil.copy2(input_video_path, output_video_path)
        if progress_cb:
            progress_cb(1.0)
        return output_video_path

    # Auto split timeline for 9:16 layout
    split_timeline = auto_split_timeline(
        timeline,
        display_mode=s.get('display_mode', '1_line'),
        max_chars_per_line=int(s.get('max_chars_per_line', 12))
    ) if show_subtitles else []

    font = _load_font(s['font_key'], s['font_size'])
    badge_font = _load_font(s['font_key'], int(s['font_size'] * 0.70))

    # Read video frames with ffmpeg pipe
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        input_video_path
    ]
    try:
        dur_res = subprocess.check_output(probe_cmd).decode('utf-8').strip()
        duration = float(dur_res)
    except Exception:
        duration = 30.0

    total_frames = int(duration * FPS)

    read_cmd = [
        'ffmpeg', '-i', input_video_path,
        '-f', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-r', str(FPS),
        '-s', f"{W}x{H}",
        'pipe:1'
    ]

    write_cmd = [
        'ffmpeg', '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f"{W}x{H}",
        '-pix_fmt', 'rgb24',
        '-r', str(FPS),
        '-i', 'pipe:0',
        '-i', input_video_path,
        '-map', '0:v:0',
        '-map', '1:a:0?',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '18',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-shortest',
        '-movflags', '+faststart',
        output_video_path
    ]

    reader_proc = subprocess.Popen(read_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    writer_proc = subprocess.Popen(write_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    stderr_buf = []
    def _read_err():
        stderr_buf.append(writer_proc.stderr.read())
    t_err = threading.Thread(target=_read_err, daemon=True)
    t_err.start()

    frame_bytes = W * H * 3
    tc = _parse_color(s['text_color'])
    oc = _parse_color(s['outline_color'])
    ow = s['outline_width']
    fw = s['font_weight']
    pos = s['position']
    b_margin = s['bottom_margin']
    t_margin = s['top_margin']
    cx = W // 2

    # Determine banner text
    banner_text = ""
    if show_banner:
        if custom_banner:
            banner_text = custom_banner
        elif clip_meta:
            banner_text = clip_meta.get('hook') or clip_meta.get('title') or ""

    try:
        for fi in range(total_frames):
            raw_frame = reader_proc.stdout.read(frame_bytes)
            if not raw_frame or len(raw_frame) < frame_bytes:
                break

            t = fi / FPS
            img = Image.frombytes('RGB', (W, H), raw_frame)
            draw = ImageDraw.Draw(img, 'RGBA')

            # 1. Top Header Badge (Hook / Title)
            if banner_text:
                b_bbox = badge_font.getbbox(banner_text)
                bw = b_bbox[2] - b_bbox[0] + 44
                bh = b_bbox[3] - b_bbox[1] + 26
                bx = cx - bw // 2
                by = t_margin
                # Rounded badge with yellow accent border
                draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=18, fill=(0, 0, 0, 190), outline=(255, 230, 0, 240), width=3)
                draw.text((cx - (b_bbox[2] - b_bbox[0]) // 2, by + 12), banner_text, font=badge_font, fill=(255, 255, 255, 255))

            # 2. Render Subtitles matching current timestamp t
            if show_subtitles and split_timeline:
                for entry in split_timeline:
                    start, end, text = entry['start'], entry['end'], entry['text']
                    if start <= t < end:
                        lines = text.split('\n')
                        line_spacing = int(font.size * 0.2)
                        total_th = sum([(font.getbbox(l)[3] - font.getbbox(l)[1]) for l in lines if l]) + line_spacing * max(0, len(lines) - 1)

                        if pos == 'bottom':
                            text_y = H - b_margin - total_th
                        elif pos == 'top':
                            text_y = t_margin + 110
                        else:
                            text_y = (H - total_th) // 2

                        _draw_outlined_text(draw, text, font, cx, text_y, tc + (255,), oc + (255,), ow, fw)
                        break

            # Write modified frame
            writer_proc.stdin.write(img.tobytes())

            if progress_cb and fi % (FPS * 2) == 0:
                progress_cb(fi / total_frames)

    finally:
        try:
            reader_proc.stdout.close()
            reader_proc.kill()
        except Exception:
            pass
        try:
            writer_proc.stdin.close()
        except Exception:
            pass
        writer_proc.wait()
        t_err.join(timeout=5)

    if progress_cb:
        progress_cb(1.0)

    return output_video_path
