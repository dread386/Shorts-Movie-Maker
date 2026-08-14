"""
video_splitter.py
-----------------
Cut clips from source video and convert to 9:16 vertical ratio (1080x1920) using FFmpeg.
Supports:
- 'center_crop': Center crop 16:9 to 9:16 (Standard)
- 'left_crop': Left-aligned crop (Ideal for Guitar left-hand / fretboard)
- 'right_crop': Right-aligned crop
- 'blur_pad': Background blur padding (Fills 9:16 without cropping instrument)
- 'fit_letterbox': Letterbox black bar padding
"""

import os
import subprocess


def extract_vertical_clip(source_video: str, start_sec: float, end_sec: float,
                          output_path: str,
                          crop_mode: str = 'center_crop',
                          target_w: int = 1080,
                          target_h: int = 1920) -> str:
    """
    Extract a clip from `source_video` between `start_sec` and `end_sec`,
    applying 9:16 vertical conversion.
    """
    if not os.path.exists(source_video):
        raise FileNotFoundError(f"Source video not found: {source_video}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    duration = max(0.5, end_sec - start_sec)

    # Filter string based on crop_mode
    if crop_mode == 'blur_pad':
        # Split into blurred 9:16 background + sharp centered 16:9 foreground
        vf_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},"
            f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2[bg];"
            f"[0:v]scale={target_w}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        filter_complex = ['-filter_complex', vf_filter, '-map', '[v]', '-map', '0:a?']
    elif crop_mode == 'left_crop':
        # Left-offset crop (Focus on left hand / guitar fretboard: x = (iw - ow) * 0.20)
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)*0.20:0,scale={target_w}:{target_h}"
        filter_complex = ['-vf', vf_filter]
    elif crop_mode == 'right_crop':
        # Right-offset crop (x = (iw - ow) * 0.80)
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)*0.80:0,scale={target_w}:{target_h}"
        filter_complex = ['-vf', vf_filter]
    elif crop_mode == 'fit_letterbox':
        vf_filter = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
        filter_complex = ['-vf', vf_filter]
    else:
        # Default: center_crop (crop 9:16 from center of video)
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
        '-crf', '20',
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
