"""Real HTTP/frontend/model smoke; no personal accounts or microphone needed."""
import json
import urllib.request


def main():
    base = "http://127.0.0.1:8000"
    def call(path, body=None):
        req = urllib.request.Request(base + "/api" + path, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", "X-Jarvis-Client": "ui"})
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.load(r)
    assert call("/health")["application"] == "jarvis-local"
    with urllib.request.urlopen(base) as response:
        assert b'<div id="root">' in response.read()
    status = call("/status")
    assert status["voice"]["tts"] and status["voice"]["stt"], status["voice"]
    config = call("/settings")
    assert "openai_key" not in config and "telegram_token" not in config
    assert status["ollama"]["connected"]
    reply = call("/chat", {"provider": "ollama", "model": config["model"], "messages": [{"role": "user", "content": "Reply with one sentence saying hello."}]})
    assert reply["text"].strip()
    print("HTTP, frontend, ready local voice engines, and real Ollama chat passed.")


if __name__ == "__main__":
    main()
