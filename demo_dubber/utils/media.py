from __future__ import annotations

from pathlib import Path

import streamlit as st


def render_video_file(video_path: Path) -> None:
    if not video_path.exists():
        st.warning(f"Video file not found: {video_path}")
        return

    mime = _guess_video_mime(video_path)
    # Let Streamlit serve the saved file instead of embedding the full video
    # bytes into the app state on each rerun.
    st.video(str(video_path), format=mime)


def _guess_video_mime(video_path: Path) -> str:
    suffix = video_path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".m4v":
        return "video/x-m4v"
    return "video/mp4"
