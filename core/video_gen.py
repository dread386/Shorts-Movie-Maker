"""
video_gen.py
------------
Burns rendered animated / outlined subtitles, multi-line auto-scaled header banners,
and generates high-CTR 9:16 vertical thumbnails using Pillow and FFmpeg.
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
    'top_margin': 180,
    'fade_in': 0.1,
    'fade_out': 0.1,
    'display_mode': '1_line',
    'max_chars_per_line': 12,
    'show_subtitles': True,
    'show_header_banner': True,
    'custom_banner_text': '',
    'banner_style': 'yellow_black' # 'yellow_black' | 'red_black' | 'simple_black'
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


def _wrap_banner_text(text: str, font_key: str, base_font_size: int, max_width: int = 940) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """
    Splits banner text into lines that fit within max_width (px).
    Automatically reduces font size if necessary.
    """
    raw_lines = text.strip().split('\n')
    current_size = base_font_size

    # Try sizes down to 32px until text fits well
    while current_size >= 32:
        font = _load_font(font_key, current_size)
        wrapped_lines = []
        fits_all = True

        for raw_line in raw_lines:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            # Check if line fits without splitting
            bbox = font.getbbox(raw_line)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_width:
                wrapped_lines.append(raw_line)
                continue

            # Word / char wrap
            curr = ""
            for ch in raw_line:
                test_str = curr + ch
                tb = font.getbbox(test_str)
                if (tb[2] - tb[0]) <= max_width:
                    curr = test_str
                else:
                    if curr:
                        wrapped_lines.append(curr)
                    curr = ch
            if curr:
                wrapped_lines.append(curr)

        # Max 3 lines for banner header
        if len(wrapped_lines) <= 3:
            return wrapped_lines, font

        # If too many lines, scale down font
        current_size -= 4

    font = _load_font(font_key, current_size)
    return wrapped_lines, font


def _draw_smart_banner(draw: ImageDraw.ImageDraw,
                       banner_text: str,
                       cx: int,
                       top_margin: int,
                       font_key: str = 'ja_kaku',
                       base_font_size: int = 50,
                       banner_style: str = 'yellow_black'):
    """
    Renders multi-line, auto-scaled high-impact hook banner at top of frame.
    """
    if not banner_text:
        return

    lines, font = _wrap_banner_text(banner_text, font_key, base_font_size, max_width=920)
    if not lines:
        return

    line_heights = []
    line_widths = []
    for l in lines:
        bb = font.getbbox(l)
        line_widths.append(bb[2] - bb[0])
        line_heights.append(bb[3] - bb[1])

    max_w = max(line_widths)
    line_spacing = int(font.size * 0.22)
    total_text_h = sum(line_heights) + line_spacing * max(0, len(lines) - 1)

    pad_x = 36
    pad_y = 22
    bw = max_w + pad_x * 2
    bh = total_text_h + pad_y * 2
    bx = cx - bw // 2
    by = top_margin

    # Style definitions
    if banner_style == 'red_black':
        bg_color = (15, 15, 20, 220)
        border_color = (255, 60, 60, 255)
        text_color = (255, 255, 255, 255)
        border_w = 4
    elif banner_style == 'simple_black':
        bg_color = (0, 0, 0, 200)
        border_color = (255, 255, 255, 180)
        text_color = (255, 255, 255, 255)
        border_w = 2
    else: # yellow_black (Classic YouTube Hook / Blew style)
        bg_color = (10, 10, 15, 225)
        border_color = (255, 220, 0, 255)
        text_color = (255, 255, 255, 255)
        border_w = 4

    # Outer subtle shadow
    draw.rounded_rectangle([bx + 4, by + 4, bx + bw + 4, by + bh + 4], radius=20, fill=(0, 0, 0, 120))
    # Main badge box
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=20, fill=bg_color, outline=border_color, width=border_w)

    # Render lines centered
    curr_y = by + pad_y
    for i, line in enumerate(lines):
        bb = font.getbbox(line)
        lw = bb[2] - bb[0]
        lh = bb[3] - bb[1]
        lx = cx - lw // 2
        
        # Slight text outline for maximum legibility
        for dx in (-2, 0, 2):
            for dy in (-2, 0, 2):
                if dx != 0 or dy != 0:
                    draw.text((lx + dx, curr_y + dy), line, font=font, fill=(0, 0, 0, 220))
        draw.text((lx, curr_y), line, font=font, fill=text_color)
        curr_y += lh + line_spacing


def _draw_outlined_text(draw, text, font, cx, y, text_rgba, outline_rgba, outline_w, font_weight=2):
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

        # Draw thick outline with dual-pass for maximum contrast
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
    Burn subtitles and multi-line auto-scaled header banner on top of vertical video (1080x1920).
    """
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    W, H, FPS = s['width'], s['height'], s['fps']
    show_subtitles = s.get('show_subtitles', True)
    show_banner = s.get('show_header_banner', True)
    custom_banner = s.get('custom_banner_text', '').strip()
    banner_style = s.get('banner_style', 'yellow_black')

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

            # 1. Top Header Badge (Multi-line Smart Auto-Scaled Banner)
            if banner_text:
                _draw_smart_banner(
                    draw=draw,
                    banner_text=banner_text,
                    cx=cx,
                    top_margin=t_margin,
                    font_key=s['font_key'],
                    base_font_size=int(s['font_size'] * 0.75),
                    banner_style=banner_style
                )

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
                            text_y = t_margin + 130
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


def generate_clip_thumbnail(video_path: str,
                            output_png_path: str,
                            banner_text: str,
                            subtitle_text: str = "",
                            settings: dict = None,
                            capture_sec: float = 0.5) -> str:
    """
    Extracts a representative frame from vertical video and renders
    a high-impact, high-CTR 9:16 thumbnail image (1080x1920 PNG).
    """
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    W, H = s['width'], s['height']
    font_key = s['font_key']
    banner_style = s.get('banner_style', 'yellow_black')
    t_margin = s.get('top_margin', 180)
    cx = W // 2

    # 1. Capture single frame with FFmpeg
    raw_frame_path = output_png_path + ".tmp.png"
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(capture_sec),
        '-i', video_path,
        '-vframes', '1',
        '-s', f"{W}x{H}",
        raw_frame_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        img = Image.open(raw_frame_path).convert('RGB')
    except Exception:
        # Fallback create dark canvas
        img = Image.new('RGB', (W, H), (20, 20, 28))
    finally:
        if os.path.exists(raw_frame_path):
            try:
                os.remove(raw_frame_path)
            except Exception:
                pass

    draw = ImageDraw.Draw(img, 'RGBA')

    # 2. Render Extra Punchy Header Banner
    if banner_text:
        _draw_smart_banner(
            draw=draw,
            banner_text=banner_text,
            cx=cx,
            top_margin=t_margin,
            font_key=font_key,
            base_font_size=56,
            banner_style=banner_style
        )

    # 3. If subtitle text is given, render a punchy bottom text
    if subtitle_text:
        sub_font = _load_font(font_key, 72)
        _draw_outlined_text(
            draw=draw,
            text=subtitle_text,
            font=sub_font,
            cx=cx,
            y=H - 420,
            text_rgba=(255, 240, 0, 255),
            outline_rgba=(0, 0, 0, 255),
            outline_w=8,
            font_weight=3
        )

    img.save(output_png_path, format='PNG', quality=95)
    return output_png_path

