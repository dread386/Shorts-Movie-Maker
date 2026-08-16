"""
video_splitter.py
-----------------
Cuts clips from source video and converts them to 9:16 vertical ratio (1080x1920) using FFmpeg.
Supports standard crop modes and 8-grid (A-H) multi-slot vertical segmentation.
"""

import os
import subprocess


# 1920x1080 resolution base grid cells (4 horizontal x 2 vertical)
GRID_CELLS = {
    # Single cells (480 x 540)
    'A': {'x': 0,    'y': 0,   'w': 480, 'h': 540, 'label': 'A (左手上・ネック)'},
    'B': {'x': 480,  'y': 0,   'w': 480, 'h': 540, 'label': 'B (中央左上)'},
    'C': {'x': 960,  'y': 0,   'w': 480, 'h': 540, 'label': 'C (中央右上・顔)'},
    'D': {'x': 1440, 'y': 0,   'w': 480, 'h': 540, 'label': 'D (右上)'},
    'E': {'x': 0,    'y': 540, 'w': 480, 'h': 540, 'label': 'E (左手下)'},
    'F': {'x': 480,  'y': 540, 'w': 480, 'h': 540, 'label': 'F (ピッキング手元)'},
    'G': {'x': 960,  'y': 540, 'w': 480, 'h': 540, 'label': 'G (ボディ/アンプ)'},
    'H': {'x': 1440, 'y': 540, 'w': 480, 'h': 540, 'label': 'H (右下)'},

    # Horizontal 2-cell wide combos (960 x 540)
    'AB': {'x': 0,    'y': 0,   'w': 960, 'h': 540, 'label': 'A+B (左上ワイド)'},
    'BC': {'x': 480,  'y': 0,   'w': 960, 'h': 540, 'label': 'B+C (中央上ワイド)'},
    'CD': {'x': 960,  'y': 0,   'w': 960, 'h': 540, 'label': 'C+D (右上ワイド)'},
    'EF': {'x': 0,    'y': 540, 'w': 960, 'h': 540, 'label': 'E+F (左下ワイド・手元)'},
    'FG': {'x': 480,  'y': 540, 'w': 960, 'h': 540, 'label': 'F+G (中央下ワイド・ギター)'},
    'GH': {'x': 960,  'y': 540, 'w': 960, 'h': 540, 'label': 'G+H (右下ワイド)'},

    # Vertical 2-cell tall combos (480 x 1080)
    'AE': {'x': 0,    'y': 0,   'w': 480, 'h': 1080, 'label': 'A+E (左端縦長)'},
    'BF': {'x': 480,  'y': 0,   'w': 480, 'h': 1080, 'label': 'B+F (中左縦長)'},
    'CG': {'x': 960,  'y': 0,   'w': 480, 'h': 1080, 'label': 'C+G (中右縦長)'},
    'DH': {'x': 1440, 'y': 0,   'w': 480, 'h': 1080, 'label': 'D+H (右端縦長)'},

    # Full / Center
    'FULL':   {'x': 0,   'y': 0, 'w': 1920, 'h': 1080, 'label': 'FULL (16:9全体)'},
    'CENTER': {'x': 480, 'y': 0, 'w': 960,  'h': 1080, 'label': 'CENTER (中央フォーカス)'}
}

GRID_LAYOUT_SLOTS = {
    'split_2_vertical':   {'label': '上下2分割 (上/下)',   'count': 2, 'dims': [(1080, 960), (1080, 960)]},
    'split_3_vertical':   {'label': '上中下3分割 (上/中/下)', 'count': 3, 'dims': [(1080, 640), (1080, 640), (1080, 640)]},
    'split_4_vertical':   {'label': '上中下4分割 (4段)',     'count': 4, 'dims': [(1080, 480), (1080, 480), (1080, 480), (1080, 480)]},
    'grid_2x2':           {'label': '2×2 タイル (4画面)',   'count': 4, 'dims': [(540, 960), (540, 960), (540, 960), (540, 960)]},
    'split_2_horizontal': {'label': '左右2分割 (左/右)',   'count': 2, 'dims': [(540, 1920), (540, 1920)]}
}


def _build_grid_filter_complex(grid_layout: str, grid_slots: list[str], target_w: int = 1080, target_h: int = 1920) -> str:
    """
    Builds FFmpeg filter complex string for multi-slot grid segmentation.
    """
    layout_info = GRID_LAYOUT_SLOTS.get(grid_layout, GRID_LAYOUT_SLOTS['split_2_vertical'])
    slot_count = layout_info['count']
    slot_dims = layout_info['dims']

    # Ensure slot list length matches count
    slots = list(grid_slots or [])
    default_defaults = ['A', 'F', 'C', 'G']
    while len(slots) < slot_count:
        slots.append(default_defaults[len(slots) % len(default_defaults)])

    filter_parts = []
    slot_names = []

    for i in range(slot_count):
        cell_key = slots[i].upper()
        cell = GRID_CELLS.get(cell_key, GRID_CELLS['A'])
        slot_w, slot_h = slot_dims[i]
        
        # Calculate proportional crop coordinates (works on any 16:9 resolution)
        # crop: iw*w/1920 : ih*h/1080 : iw*x/1920 : ih*y/1080
        cw = cell['w']
        ch = cell['h']
        cx = cell['x']
        cy = cell['y']

        slot_label = f"slot_{i}"
        part = (
            f"[0:v]crop=iw*{cw}/1920:ih*{ch}/1080:iw*{cx}/1920:ih*{cy}/1080,"
            f"scale={slot_w}:{slot_h}:force_original_aspect_ratio=increase,crop={slot_w}:{slot_h}[{slot_label}]"
        )
        filter_parts.append(part)
        slot_names.append(f"[{slot_label}]")

    # Combine slots
    if grid_layout == 'split_2_vertical':
        comb = f"{slot_names[0]}{slot_names[1]}vstack=inputs=2[v]"
    elif grid_layout == 'split_3_vertical':
        comb = f"{slot_names[0]}{slot_names[1]}{slot_names[2]}vstack=inputs=3[v]"
    elif grid_layout == 'split_4_vertical':
        comb = f"{slot_names[0]}{slot_names[1]}{slot_names[2]}{slot_names[3]}vstack=inputs=4[v]"
    elif grid_layout == 'split_2_horizontal':
        comb = f"{slot_names[0]}{slot_names[1]}hstack=inputs=2[v]"
    elif grid_layout == 'grid_2x2':
        comb = f"{slot_names[0]}{slot_names[1]}hstack=inputs=2[row_top];{slot_names[2]}{slot_names[3]}hstack=inputs=2[row_bot];[row_top][row_bot]vstack=inputs=2[v]"
    else:
        comb = f"{slot_names[0]}{slot_names[1]}vstack=inputs=2[v]"

    filter_parts.append(comb)
    return ';'.join(filter_parts)


def extract_vertical_clip(source_video: str, start_sec: float, end_sec: float,
                          output_path: str,
                          crop_mode: str = 'blur_pad',
                          grid_layout: str = 'split_2_vertical',
                          grid_slots: list[str] = None,
                          target_w: int = 1080,
                          target_h: int = 1920) -> str:
    """
    Extract a clip from `source_video` between `start_sec` and `end_sec`,
    applying 9:16 vertical conversion with optional 8-grid segmentation.
    """
    if not os.path.exists(source_video):
        raise FileNotFoundError(f"Source video not found: {source_video}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    duration = max(0.5, end_sec - start_sec)

    # 1. Grid Segmentation Mode
    if crop_mode == 'grid_split':
        vf_filter = _build_grid_filter_complex(grid_layout, grid_slots or ['A', 'F'], target_w, target_h)
        filter_complex = ['-filter_complex', vf_filter, '-map', '[v]', '-map', '0:a?']

    # 2. Standard Modes
    elif crop_mode == 'blur_pad':
        vf_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},"
            f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2[bg];"
            f"[0:v]scale={target_w}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        filter_complex = ['-filter_complex', vf_filter, '-map', '[v]', '-map', '0:a?']
    elif crop_mode == 'left_crop':
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)*0.20:0,scale={target_w}:{target_h}"
        filter_complex = ['-vf', vf_filter]
    elif crop_mode == 'right_crop':
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)*0.80:0,scale={target_w}:{target_h}"
        filter_complex = ['-vf', vf_filter]
    elif crop_mode == 'fit_letterbox':
        vf_filter = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
        filter_complex = ['-vf', vf_filter]
    else:
        # Default: center_crop
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)/2:0,scale={target_w}:{target_h}"
        filter_complex = ['-vf', vf_filter]

    cmd = [
        'ffmpeg', '-y',
        '-ss', f"{start_sec:.2f}",
        '-t', f"{duration:.2f}",
        '-i', source_video,
        *filter_complex,
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '19',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-movflags', '+faststart',
        output_path
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode != 0:
        err_msg = res.stderr.decode('utf-8', errors='ignore')
        raise RuntimeError(f"FFmpeg clip extraction failed:\n{err_msg[-1000:]}")

    return output_path
