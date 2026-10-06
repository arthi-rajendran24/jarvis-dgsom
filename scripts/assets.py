"""Pinned official runtime/voice artifacts. No downloaded executables are committed."""
UV_VERSION = "0.10.6"
PYTHON_VERSION = "3.11.14"
NODE_VERSION = "22.22.3"
OLLAMA_VERSION = "0.35.0"
WHISPER_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
STARTER_MODEL = "qwen3:0.6b"
VC_URL = "https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe"
VC_SHA = "cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b"

NODE = {
    "darwin-arm64": ("darwin-arm64.tar.gz", "0da7ff74ef8611328c8212f17943368713a2ad953fb7d89a8c8a0eae87c23207"),
    "darwin-x64": ("darwin-x64.tar.gz", "45830ba752fa0d892c6dcd640946669801293cac820a33591ded40ac075198ec"),
    "windows-x64": ("win-x64.zip", "6c8d54f635feff4df76c2ca80f45332eb2ff57d25226edce36592e51a177ee33"),
}
OLLAMA = {
    "darwin-arm64": ("ollama-darwin.tgz", "2608dbb0a0f0136a198db9d48b4f74ece55f452314a39452fca35b7cf20c2589"),
    "darwin-x64": ("ollama-darwin.tgz", "2608dbb0a0f0136a198db9d48b4f74ece55f452314a39452fca35b7cf20c2589"),
    "windows-x64": ("ollama-windows-amd64.zip", "d6f7d3dd4f5d013553a78c1e78b2521fcf41d43dd2863e4596cdc046fe6036db"),
}
VOICE = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
