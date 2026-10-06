"""Native local microphone service. Keeps working when the dashboard closes."""
import io
import queue
import re
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from . import voice
from .config import load, save

RATE = 16000


class DesktopVoice:
    def __init__(self):
        self.enabled = False
        self.mode = "standby"
        self.level = 0.0
        self.error = ""
        self.last_heard = ""
        self.history = []
        self.armed_until = 0.0
        self.stream = None
        self.thread = None
        self.queue = queue.Queue(maxsize=2)
        self.parts = []
        self.preroll = []
        self.silence = 0.0
        self.samples = 0
        self.busy = False
        self.respond = None
        self.latency = None

    def state(self):
        return {"enabled": self.enabled, "mode": self.mode, "level": self.level, "error": self.error, "last_heard": self.last_heard, "messages": self.history[-30:], "latency": self.latency}

    def start(self, respond):
        if self.enabled:
            return self.state()
        if self.thread and self.thread.is_alive():
            raise RuntimeError("The previous desktop request is finishing. Try again in a moment.")
        if not voice.stt or not voice.tts:
            raise RuntimeError("Voice engines are still loading. Try again when Kokoro and Whisper are ready.")
        self.respond = respond
        self.error = ""
        self.queue = queue.Queue(maxsize=2)
        self.parts = []
        self.preroll = []
        self.samples = 0
        self.silence = 0
        self.busy = False
        self.armed_until = 0
        try:
            self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=2048, callback=self.capture)
            self.stream.start()
        except Exception:
            if self.stream:
                self.stream.close()
            raise RuntimeError("Desktop microphone could not start. Allow microphone access for Terminal/Python in macOS Privacy & Security, or enable microphone access for desktop apps in Windows Privacy settings. Select a default input device in Sound settings.")
        self.enabled = True
        self.thread = threading.Thread(target=self.worker, daemon=True, name="jarvis-microphone")
        self.thread.start()
        save({"desktop_voice": True})
        return self.state()

    def stop(self):
        self.enabled = False
        sd.stop()
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.mode = "standby"
        self.level = 0
        self.armed_until = 0
        save({"desktop_voice": False})
        return self.state()

    def capture(self, data, frames, timing, stream_status):
        if not self.enabled or self.busy:
            self.parts = []
            self.preroll = []
            self.samples = 0
            self.silence = 0
            return
        if self.armed_until and time.monotonic() > self.armed_until:
            self.mode = "standby"
            self.armed_until = 0
        chunk = data[:, 0].copy()
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        self.level = min(1.0, rms * 12)
        if not self.parts:
            self.preroll.append(chunk)
            self.preroll = self.preroll[-3:]
        if rms > 0.012:
            if not self.parts:
                self.parts = list(self.preroll)
                self.samples = sum(len(c) for c in self.parts)
                self.preroll = []
            else:
                self.parts.append(chunk)
                self.samples += frames
            self.silence = 0
        elif self.parts:
            self.parts.append(chunk)
            self.samples += frames
            self.silence += frames / RATE
        if self.parts and (self.silence > .8 or self.samples / RATE > 18):
            if self.samples / RATE > .4:
                try:
                    self.queue.put_nowait(np.concatenate(self.parts))
                except queue.Full:
                    pass
            self.parts = []
            self.samples = 0
            self.silence = 0

    def say(self, text):
        if not self.enabled:
            return
        c = load()
        wav = voice.speak(re.sub(r"[*#`]", "", text)[:6000], c["voice"], c["speed"])
        if not self.enabled:
            return
        audio, rate = sf.read(io.BytesIO(wav), dtype="float32")
        self.mode = "speaking"
        sd.play(audio, rate)
        start = time.monotonic()
        duration = len(audio) / rate
        while self.enabled and time.monotonic() - start < duration:
            position = int((time.monotonic() - start) * rate)
            window = audio[position:position + rate // 20]
            self.level = min(1.0, float(np.sqrt(np.mean(window * window))) * 5) if len(window) else 0
            time.sleep(.05)
        if not self.enabled:
            sd.stop()
        else:
            sd.wait()
        self.level = 0

    def worker(self):
        while self.enabled:
            try:
                samples = self.queue.get(timeout=.5)
            except queue.Empty:
                continue
            self.busy = True
            try:
                wav = io.BytesIO()
                sf.write(wav, samples, RATE, format="WAV")
                text = voice.transcribe(wav.getvalue())
                if not self.enabled:
                    break
                self.last_heard = text
                match = re.search(r"\b(?:hey\s+)?jarvis\b[\s,.!?:-]*", text, re.I)
                command = text[match.end():].strip() if match else (text if time.monotonic() < self.armed_until else "")
                if match and not command:
                    self.say("Yes, I'm listening.")
                    self.armed_until = time.monotonic() + 12
                    self.mode = "listening"
                elif command:
                    self.armed_until = 0
                    self.mode = "thinking"
                    self.history.append({"role": "user", "content": command, "time": time.strftime("%I:%M %p")})
                    started = time.monotonic()
                    reply = self.respond(self.history[-30:])
                    self.latency = round(time.monotonic() - started, 2)
                    self.history.append({"role": "assistant", "content": reply, "time": time.strftime("%I:%M %p")})
                    self.history = self.history[-30:]
                    self.say(reply)
                    self.mode = "standby"
                self.error = ""
            except Exception as exc:
                self.error = str(exc.detail) if hasattr(exc, "detail") else "Desktop voice failed. Check your model and microphone in settings."
                self.mode = "standby"
            finally:
                self.busy = False
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        break


desktop = DesktopVoice()
