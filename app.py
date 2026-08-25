from __future__ import annotations

import logging
import warnings

import streamlit as st

from demo_dubber.config import get_settings
from demo_dubber.ui.render_panel import process_render, render_result_panel
from demo_dubber.ui.transcript_editor import render_transcript_editor
from demo_dubber.ui.upload import process_transcription, render_upload_panel
from demo_dubber.utils.files import ensure_directories

warnings.filterwarnings(
    "ignore",
    message="dropout option adds dropout after all but last recurrent layer.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="`torch.nn.utils.weight_norm` is deprecated.*",
    category=FutureWarning,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> None:
    settings = get_settings()
    ensure_directories(settings.outputs_dir)

    st.set_page_config(
        page_title="Demo Dubber",
        page_icon="🎙️",
        layout="wide",
    )
    st.title("Demo Dubber")
    st.caption("Timestamp-aware demo video dubbing with Whisper and Kokoro.")

    if "stage" not in st.session_state:
        st.session_state["stage"] = "upload"

    error = st.session_state.get("error")
    if error:
        st.error(error)

    stage = st.session_state["stage"]
    if stage == "upload":
        render_upload_panel(settings)
    elif stage == "processing_transcript":
        process_transcription(settings)
    elif stage == "edit":
        render_transcript_editor(settings)
    elif stage == "processing_render":
        process_render(settings)
    elif stage == "result":
        render_result_panel(settings)
    else:
        st.session_state["stage"] = "upload"
        st.rerun()


if __name__ == "__main__":
    main()
