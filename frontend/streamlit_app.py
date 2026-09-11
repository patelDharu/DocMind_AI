# frontend/streamlit_app.py

import streamlit as st
import requests

from audio_recorder_streamlit import audio_recorder


API_URL = "http://localhost:8000"


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="DocMind AI",
    page_icon="📄",
    layout="wide",
)

st.title("📄 DocMind AI — Trilingual Document Intelligence")

st.caption(
    "Ask questions from your documents in English, Hindi, "
    "or Gujarati — by typing or speaking."
)


# =========================================================
# CONSTANTS
# =========================================================

CONFIDENCE_BADGE = {
    "high": "🟢 High confidence",
    "medium": "🟡 Medium confidence",
    "low": "🔴 Low confidence",
}

LANG_CODE = {
    "Auto-detect": None,
    "English": "en",
    "Hindi (हिन्दी)": "hi",
    "Gujarati (ગુજરાતી)": "gu",
}


# =========================================================
# SESSION STATE
# =========================================================

if "current_document_id" not in st.session_state:
    st.session_state.current_document_id = None

if "current_document_name" not in st.session_state:
    st.session_state.current_document_name = None

if "documents" not in st.session_state:
    st.session_state.documents = {}


# =========================================================
# HELPER: GET DOCUMENTS
# =========================================================

def get_documents():
    """
    Get indexed documents from backend.

    The current backend can reconstruct document information
    from ChromaDB metadata.
    """

    try:
        response = requests.get(
            f"{API_URL}/documents",
            timeout=10,
        )

        if response.ok:
            data = response.json()

            return data.get(
                "documents",
                [],
            )

    except requests.RequestException:
        pass

    return []


# =========================================================
# HELPER: RENDER RESULT
# =========================================================

def render_result(result: dict):

    st.markdown("### Answer")

    st.write(
        result.get(
            "answer",
            "No answer returned.",
        )
    )

    confidence = result.get(
        "confidence",
        "medium",
    )

    st.caption(
        CONFIDENCE_BADGE.get(
            confidence,
            "",
        )
    )

    # -----------------------------------------------------
    # Sources
    # -----------------------------------------------------

    sources = result.get(
        "sources",
        [],
    )

    if sources:

        st.markdown("### Sources")

        for source in sources:

            st.write(
                f"- **{source['source']}**, "
                f"page {source['page']} "
                f"(relevance: {source['score']})"
            )


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("📚 Documents")


# =========================================================
# UPLOAD DOCUMENT
# =========================================================

uploaded_file = st.sidebar.file_uploader(
    "Choose a PDF, DOCX, TXT, or MD file",
    type=[
        "pdf",
        "docx",
        "txt",
        "md",
    ],
)


if uploaded_file:

    if st.sidebar.button(
        "📥 Index document",
        use_container_width=True,
    ):

        with st.spinner(
            "Chunking, embedding, and indexing..."
        ):

            try:

                files = {
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                    )
                }

                response = requests.post(
                    f"{API_URL}/upload",
                    files=files,
                    timeout=300,
                )

                if response.ok:

                    data = response.json()

                    document_id = data[
                        "document_id"
                    ]

                    filename = data[
                        "filename"
                    ]

                    # -----------------------------------------
                    # Make newly uploaded document current
                    # -----------------------------------------

                    st.session_state.current_document_id = (
                        document_id
                    )

                    st.session_state.current_document_name = (
                        filename
                    )

                    st.sidebar.success(
                        f"Indexed {data['chunks_indexed']} "
                        f"chunks from {filename}"
                    )

                    st.sidebar.info(
                        "This document is now selected."
                    )

                else:

                    st.sidebar.error(
                        response.text
                    )

            except requests.RequestException as e:

                st.sidebar.error(
                    f"Backend connection error: {e}"
                )


# =========================================================
# DOCUMENT SELECTION
# =========================================================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "🔎 Search scope"
)


documents = get_documents()


# ---------------------------------------------------------
# Build document options
# ---------------------------------------------------------

document_options = {
    "🌐 All documents": None
}

for document in documents:

    document_id = document.get(
        "document_id"
    )

    filename = document.get(
        "filename",
        "Unknown document",
    )

    if document_id:
        document_options[
            f"📄 {filename}"
        ] = document_id


# ---------------------------------------------------------
# Determine default selection
# ---------------------------------------------------------

default_index = 0

if st.session_state.current_document_id:

    for index, (
        label,
        doc_id,
    ) in enumerate(
        document_options.items()
    ):

        if (
            doc_id
            == st.session_state.current_document_id
        ):
            default_index = index
            break


selected_label = st.sidebar.selectbox(
    "Select document",
    list(document_options.keys()),
    index=default_index,
)


selected_document_id = document_options[
    selected_label
]


# ---------------------------------------------------------
# Update session state
# ---------------------------------------------------------

if selected_document_id:

    st.session_state.current_document_id = (
        selected_document_id
    )

    st.session_state.current_document_name = (
        selected_label.replace(
            "📄 ",
            "",
        )
    )

else:

    st.session_state.current_document_id = None

    st.session_state.current_document_name = None


# =========================================================
# CURRENT DOCUMENT STATUS
# =========================================================

if st.session_state.current_document_id:

    st.sidebar.success(
        f"Searching only:\n\n"
        f"**{st.session_state.current_document_name}**"
    )

else:

    st.sidebar.warning(
        "Searching across all indexed documents."
    )


# =========================================================
# MAIN: TYPED QUESTION
# =========================================================

st.subheader(
    "⌨️ Ask by typing"
)


lang_choice = st.selectbox(
    "Answer language",
    list(LANG_CODE.keys()),
)


question = st.text_input(
    "Your question (English / हिन्दी / ગુજરાતી)"
)


if st.button(
    "Ask",
    type="primary",
) and question:

    with st.spinner(
        "Retrieving and generating answer..."
    ):

        try:

            response = requests.post(
                f"{API_URL}/ask",
                json={
                    "question": question,
                    "lang_hint": LANG_CODE[
                        lang_choice
                    ],
                    "document_id": (
                        st.session_state.current_document_id
                    ),
                    "top_k": 8,
                },
                timeout=120,
            )

            if response.ok:

                render_result(
                    response.json()
                )

            else:

                st.error(
                    response.text
                )

        except requests.RequestException as e:

            st.error(
                f"Backend connection error: {e}"
            )


# =========================================================
# DIVIDER
# =========================================================

st.divider()


# =========================================================
# MAIN: VOICE QUESTION
# =========================================================

st.subheader(
    "🎤 Ask by speaking"
)

st.caption(
    "Record your question in English, Hindi, or Gujarati. "
    "The system will automatically detect the language."
)


audio_bytes = audio_recorder(
    text="Click to record",
    recording_color="#e8483e",
    neutral_color="#444",
)


if audio_bytes:

    st.audio(
        audio_bytes,
        format="audio/wav",
    )

    if st.button(
        "🎙️ Transcribe and answer",
    ):

        with st.spinner(
            "Transcribing and generating answer..."
        ):

            try:

                files = {
                    "file": (
                        "question.wav",
                        audio_bytes,
                        "audio/wav",
                    )
                }

                response = requests.post(
                    f"{API_URL}/ask-voice",
                    files=files,
                    params={
                        "document_id": (
                            st.session_state.current_document_id
                        ),
                        "speak_reply": True,
                    },
                    timeout=180,
                )

                if response.ok:

                    result = response.json()

                    # -----------------------------------------
                    # Transcription
                    # -----------------------------------------

                    st.info(
                        f'Heard: '
                        f'"{result.get("transcribed_question", "")}" '
                        f'(detected: '
                        f'{result.get("detected_language", "unknown")})'
                    )

                    # -----------------------------------------
                    # Answer
                    # -----------------------------------------

                    render_result(
                        result
                    )

                    # -----------------------------------------
                    # Audio reply
                    # -----------------------------------------

                    audio_reply_path = result.get(
                        "audio_reply_path"
                    )

                    if audio_reply_path:

                        filename = (
                            audio_reply_path
                            .replace("\\", "/")
                            .split("/")[-1]
                        )

                        audio_response = requests.get(
                            f"{API_URL}/audio/{filename}",
                            timeout=30,
                        )

                        if audio_response.ok:

                            st.markdown(
                                "### 🔊 Listen to the answer"
                            )

                            st.audio(
                                audio_response.content,
                                format="audio/mp3",
                            )

                else:

                    st.error(
                        response.text
                    )

            except requests.RequestException as e:

                st.error(
                    f"Backend connection error: {e}"
                )