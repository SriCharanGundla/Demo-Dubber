from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def ensure_directories(*directories: Path) -> None:
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def slugify_stem(filename: str) -> str:
    stem = Path(filename).stem.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "demo-video"


def safe_filename(filename: str) -> str:
    """Return a server-safe basename for an untrusted upload filename."""
    normalized = filename.replace("\\", "/")
    basename = Path(normalized).name.strip()
    if not basename or basename in {".", ".."} or "\x00" in basename:
        raise ValueError("The uploaded file has an invalid filename.")
    return basename


def ensure_path_within(root: Path, candidate: Path) -> Path:
    """Resolve candidate and reject paths outside root."""
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError(f"Path is outside the configured data directory: {candidate}")
    return resolved_candidate


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(payload, indent=indent))


def output_dir_for_upload(outputs_root: Path, filename: str) -> Path:
    return outputs_root / slugify_stem(filename)
