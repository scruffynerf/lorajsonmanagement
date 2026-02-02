"""
Hashing utilities for model management, supporting SHA-256, BLAKE3, CRC32, and AutoV2/V3.

Tested in: tests/test_hashing.py
"""

import hashlib
import zlib
import os
from pathlib import Path
from typing import Optional, Tuple

try:
    from blake3 import blake3
except ImportError:
    # Fallback to a placeholder or error out if critical
    # Based on the user's scripts, blake3 is expected.
    blake3 = None


def compute_file_sha256(filepath: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_autov3_hex(path: Path) -> Optional[str]:
    """
    Compute SHA-256 over the file bytes after the safetensors header (offset = header_size + 8).
    Returns full hex digest (not truncated).
    """
    try:
        with open(path, "rb") as f:
            header8 = f.read(8)
            if len(header8) < 8:
                return None
            header_size = int.from_bytes(header8, "little")
            offset = header_size + 8
            
            f.seek(0, 2)
            filesize = f.tell()
            if offset >= filesize:
                return None
                
            f.seek(offset)
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
            return h.hexdigest()
    except Exception:
        return None


def get_autov3_hash(path: Path) -> Optional[str]:
    """Get the 12-character AutoV3 hash."""
    digest = compute_autov3_hex(path)
    return digest[:12] if digest else None


def file_hashes(path: str, chunk_size=1024 * 1024) -> Tuple[Optional[str], Optional[str]]:
    """
    Calculate CRC32 and BLAKE3 for a file.
    Returns (CRC32_HEX, BLAKE3_HEX).
    """
    if not os.path.isfile(path):
        return None, None

    crc = 0
    if blake3:
        h = blake3()
    else:
        h = None
    
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            crc = zlib.crc32(chunk, crc)
            if h:
                h.update(chunk)

    crc_hex = str(format(crc & 0xFFFFFFFF, "08x")).upper()
    blake3_hex = str(h.hexdigest()).upper() if h else None
    return crc_hex, blake3_hex


def compute_key_hash(keys_with_shapes: set[str]) -> str:
    """Compute a hash from sorted layer keys (including shapes)."""
    sorted_keys = sorted(keys_with_shapes)
    key_string = '\n'.join(sorted_keys)
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()
