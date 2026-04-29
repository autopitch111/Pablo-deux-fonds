"""Video processing: cut at 6s, hook overlay, append meme (fill or fit)."""
import os
from typing import Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips

CUT_SECONDS = 6


def _make_hook_overlay(text: str, width: int, height: int, duration: float,
                       position: str = "center") -> ImageClip:
    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = max(16, int(height * 0.025))
    font = None
    for fc in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(fc):
            try: font = ImageFont.truetype(fc, font_size); break
            except: pass
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 8
    cx = (width - tw) // 2
    if position == "top":
        cy = int(height * 0.08)
    elif position == "bottom":
        cy = int(height * 0.82)
    else:
        cy = (height - th) // 2

    draw.rounded_rectangle([cx - pad_x, cy - pad_y, cx + tw + pad_x, cy + th + pad_y],
                            radius=8, fill=(0, 0, 0, 155))
    draw.text((cx + 1, cy + 1), text, font=font, fill=(0, 0, 0, 180))
    draw.text((cx,     cy),     text, font=font, fill=(255, 255, 255, 255))
    return ImageClip(np.array(img), duration=duration)


def _fit_meme(meme: VideoFileClip, target_w: int, target_h: int) -> VideoFileClip:
    """Resize meme keeping aspect ratio, centered on black background."""
    ratio  = min(target_w / meme.w, target_h / meme.h)
    new_w  = int(meme.w * ratio)
    new_h  = int(meme.h * ratio)
    meme_r = meme.resized((new_w, new_h))
    bg     = ColorClip(size=(target_w, target_h), color=[0, 0, 0], duration=meme.duration)
    x      = (target_w - new_w) // 2
    y      = (target_h - new_h) // 2
    return CompositeVideoClip([bg, meme_r.with_position((x, y))],
                              size=(target_w, target_h))


def process_video(
    video_path: str,
    meme_path: Optional[str],
    hook_text: str,
    output_path: str,
    progress_callback=None,
    meme_mode: str = "fill",
    cut_seconds: int = CUT_SECONDS,
    hook_position: str = "center",
    no_hook: bool = False,
    remove_watermark: bool = False,
) -> str:
    def cb(m):
        if progress_callback: progress_callback(m)

    cb("Chargement de la vidéo originale…")
    original = VideoFileClip(video_path)
    fps      = original.fps or 30
    cut_at   = min(cut_seconds, original.duration)

    cb(f"Coupe à {cut_at:.1f}s…")
    clip = original.subclipped(0, cut_at)

    if remove_watermark:
        cb("Suppression du filigrane…")
        orig_w, orig_h = clip.w, clip.h
        clip = clip.cropped(x1=0, y1=0, x2=orig_w, y2=int(orig_h * 0.88)).resized((orig_w, orig_h))

    if no_hook:
        clip_with_hook = clip.with_fps(fps)
    else:
        cb("Ajout du hook…")
        overlay        = _make_hook_overlay(hook_text, clip.w, clip.h, cut_at, position=hook_position)
        clip_with_hook = CompositeVideoClip([clip, overlay], size=(clip.w, clip.h)).with_fps(fps)

    parts = [clip_with_hook]

    if meme_path and os.path.exists(meme_path):
        cb(f"Chargement du mème ({meme_mode})…")
        meme = VideoFileClip(meme_path)
        if meme_mode == "fit":
            meme = _fit_meme(meme, clip.w, clip.h)
        else:
            if meme.w != clip.w or meme.h != clip.h:
                meme = meme.resized((clip.w, clip.h))
        parts.append(meme.with_fps(fps))
        cb(f"Assemblage : {cut_at:.1f}s vidéo + {meme.duration:.1f}s mème…")

    final = concatenate_videoclips(parts)
    cb("Export en cours…")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=fps, logger=None)

    for c in parts + [original, final]:
        try: c.close()
        except: pass

    cb("Export terminé !")
    return output_path
