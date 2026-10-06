"""Preload and exercise the actual local synthesis/recognition engines."""
from backend import voice


def main():
    voice.warmup()
    if not voice.status()["tts"] or not voice.status()["stt"]:
        raise RuntimeError(voice.status()["error"])
    audio = voice.speak("Jarvis, tell me the time.", "bm_george", 1)
    transcript = voice.transcribe(audio)
    if "jarvis" not in transcript.lower() or "time" not in transcript.lower():
        raise RuntimeError("Voice round-trip did not recognize the synthetic test phrase.")
    print("Kokoro synthesis and local Whisper recognition passed the synthetic voice check.")


if __name__ == "__main__":
    main()
