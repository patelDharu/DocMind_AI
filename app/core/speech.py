from functools import lru_cache
from faster_whisper import WhisperModel


@lru_cache(maxsize=1)
def get_whisper_model():
    """
    Load Whisper model once and reuse it.
    CPU + int8 keeps memory usage lower.
    """

    return WhisperModel(
        "base",
        device="cpu",
        compute_type="int8"
    )


def transcribe_audio(
    audio_path: str,
    language: str | None = None
) -> dict:
    """
    Transcribe an audio file using faster-whisper.

    Returns:
        {
            "text": "...",
            "language": "en",
            "segments": [...]
        }
    """

    model = get_whisper_model()

    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True
    )

    segment_list = []

    for segment in segments:
        segment_list.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip()
        })

    text = " ".join(
        segment["text"]
        for segment in segment_list
    ).strip()

    return {
        "text": text,
        "language": info.language,
        "language_probability": round(
            info.language_probability,
            4
        ),
        "segments": segment_list
    }