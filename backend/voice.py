import io
import threading
from pathlib import Path

import soundfile as sf

from .config import DATA

MODEL_DIR = DATA / "models"
MODEL_DIR.mkdir(exist_ok=True)
tts_lock = threading.Lock()
stt_lock = threading.Lock()
tts = None
stt = None
error = ""
loading = False


def warmup():
    global tts, stt, error, loading
    loading = True
    try:
        from kokoro_onnx import Kokoro
        from faster_whisper import WhisperModel
        from huggingface_hub import snapshot_download
        from scripts.assets import VOICE, WHISPER_REVISION
        from scripts.downloads import download
        for name, checksum in VOICE.items():
            download("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/" + name, MODEL_DIR / name, checksum)
        tts = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
        options = {"revision": WHISPER_REVISION, "cache_dir": str(MODEL_DIR / "whisper"), "allow_patterns": ["config.json", "model.bin", "tokenizer.json", "vocabulary.*"]}
        try:
            snapshot = snapshot_download("Systran/faster-whisper-base.en", local_files_only=True, **options)
        except Exception:
            snapshot = snapshot_download("Systran/faster-whisper-base.en", **options)
        stt = WhisperModel(snapshot, device="cpu", compute_type="int8")
        error = ""
    except Exception as exc:
        error = f"Voice initialization failed ({type(exc).__name__}). Run the voice setup again; see README."
    finally:
        loading = False


def status():
    return {"tts": tts is not None, "stt": stt is not None, "loading": loading, "error": error, "engine": "Kokoro 82M", "recognizer": "Whisper · local"}


def speak(text, voice, speed):
    if tts is None:
        raise RuntimeError("Kokoro is still loading. Check Voice engine in settings.")
    with tts_lock:
        samples, rate = tts.create(text, voice=voice, speed=speed, lang="en-gb" if voice.startswith("b") else "en-us")
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV")
    return buf.getvalue()


def transcribe(audio):
    if stt is None:
        raise RuntimeError("Local speech recognition is still loading.")
    with stt_lock:
        segments, _ = stt.transcribe(io.BytesIO(audio), language="en", beam_size=3, vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
