from pathlib import Path
import uuid

from gtts import gTTS


def synthesize_speech(
    text: str,
    language: str = "en",
    output_dir: str = "app/data/audio_out",
):
    """
    Convert text to speech using Google TTS.
    """

    output_path = Path(output_dir)

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"tts_{uuid.uuid4().hex}.mp3"
    )

    file_path = output_path / filename

    # gTTS supports these language codes:
    # en = English
    # hi = Hindi
    # gu = Gujarati

    supported_languages = {
        "en": "en",
        "hi": "hi",
        "gu": "gu",
    }

    language = supported_languages.get(
        language,
        "en",
    )

    tts = gTTS(
        text=text,
        lang=language,
        slow=False,
    )

    tts.save(
        str(file_path)
    )

    return str(file_path)