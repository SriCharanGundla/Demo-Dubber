from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from demo_dubber.config import get_settings
from demo_dubber.services.project_store import scan_saved_projects

TRANSIENT_DIRECTORIES = ("editor_previews", "segments", "transcription_chunks")
TRANSIENT_FILES = ("render_progress.json",)


def cleanup_generated(
    outputs_dir: Path, *, older_than_days: float, apply: bool
) -> list[Path]:
    cutoff = time.time() - older_than_days * 86_400
    projects, _errors = scan_saved_projects(outputs_dir)
    candidates: list[Path] = []
    for project in projects:
        paths = [project.output_dir / name for name in TRANSIENT_DIRECTORIES]
        paths.extend(project.output_dir / name for name in TRANSIENT_FILES)
        for path in paths:
            if path.exists() and path.stat().st_mtime < cutoff:
                candidates.append(path)
                if apply:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove old generated previews and intermediate render files."
    )
    parser.add_argument("--older-than-days", type=float, default=30, help="Default: 30")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete matching files. Without this flag, only list them.",
    )
    args = parser.parse_args()
    removed = cleanup_generated(
        get_settings().outputs_dir,
        older_than_days=args.older_than_days,
        apply=args.apply,
    )
    action = "Removed" if args.apply else "Would remove"
    for path in removed:
        print(f"{action}: {path}")
    print(f"{action} {len(removed)} generated path(s).")


if __name__ == "__main__":
    main()
