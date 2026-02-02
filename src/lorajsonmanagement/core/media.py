"""
Media processing logic for model previews, supporting image conversion and video frame extraction.

Note: Untested automatedly (Requires local FFmpeg/Pillow and media assets). Checked via: manual workflow.
"""

import os
import subprocess
import shutil
import requests
from pathlib import Path
from typing import Optional


def download_image(url: str, dest: Path, verbose: bool = False) -> bool:
    """Download an image from a URL to a local path."""
    try:
        response = requests.get(url, timeout=20, stream=True)
        response.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return dest.exists()
    except Exception as e:
        if verbose:
            print(f"❌ Failed to download image from {url}: {e}")
        return False

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import ffmpeg as ffmpeg_wrapper
except ImportError:
    ffmpeg_wrapper = None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available as a library or binary."""
    if ffmpeg_wrapper is not None:
        return True
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def extract_frame_from_video(src: Path, dest: Path, verbose: bool = False) -> bool:
    """Extract the first frame from a video file to JPEG."""
    if ffmpeg_wrapper is not None:
        try:
            (ffmpeg_wrapper
                .input(str(src), ss=0)
                .output(str(dest), vframes=1)
                .overwrite_output()
                .run(quiet=not verbose))
            return dest.exists()
        except Exception:
            return False
    else:
        try:
            cmd = ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(dest)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return dest.exists()
        except Exception:
            return False


def convert_image_to_jpeg(src: Path, dest: Path, verbose: bool = False) -> bool:
    """Convert an image file to JPEG using Pillow."""
    if Image is None:
        return False
    try:
        with Image.open(src) as im:
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                # For RGBA, mask is the 4th channel. For LA, it's the 2nd channel.
                mask = im.split()[3] if im.mode == "RGBA" else (im.split()[1] if im.mode == "LA" else None)
                bg.paste(im, mask=mask)
                bg.save(dest, format="JPEG", quality=90)
            else:
                rgb = im.convert("RGB")
                rgb.save(dest, format="JPEG", quality=90)
        return dest.exists()
    except Exception:
        return False


def find_preview_source(directory: Path, base: str) -> Optional[Path]:
    """Look for preview file candidates next to a model file."""
    candidates = [
        f"{base}.preview.webp", f"{base}.webp", 
        f"{base}.png", f"{base}.jpg", 
        f"{base}.jpeg", f"{base}.mp4"
    ]
    for c in candidates:
        p = directory / c
        if p.exists():
            return p
    return None
