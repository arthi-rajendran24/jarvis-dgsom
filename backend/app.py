import asyncio
import json
import re
import os
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import services, voice
from .config import ROOT, load, save
from .desktop import desktop

gateway_error = ""
desktop_loop = None


async def gateway():
    global gateway_error
    while True:
        try:
            c = load()
            if c["telegram_gateway"] and c["telegram_chat_id"] and c["telegram_token"]:
                for m in await services.telegram_messages():
                    if m["text"] == "/start":
                        reply = "Jarvis is online. Messages here use your selected model. Change model or disable replies in the local dashboard."
                    else:
                        reply = await services.chat_reply([{"role": "user", "content": m["text"]}], c["provider"], c["model"])
                    await services.telegram("sendMessage", {"chat_id": c["telegram_chat_id"], "text": reply[:4000]})
                gateway_error = ""
        except Exception:
            gateway_error = "Telegram reply failed. Check the selected model and connection settings."
        await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app):
    global desktop_loop
    desktop_loop = asyncio.get_running_loop()
    init = asyncio.create_task(asyncio.to_thread(voice.warmup))
    bot = asyncio.create_task(gateway())
    async def resume_desktop():
        await init
        if load()["desktop_voice"]:
            try:
                await asyncio.to_thread(desktop.start, desktop_dispatch)
            except RuntimeError as e:
                desktop.error = str(e)
    resume = asyncio.create_task(resume_desktop())
    yield
    bot.cancel()
    resume.cancel()
    # Preserve the saved desktop preference across a normal service restart.
    if desktop.enabled:
        desktop.enabled = False
        if desktop.stream:
            desktop.stream.close()
    init.cancel()


app = FastAPI(title="JARVIS Local API", lifespan=lifespan)


@app.middleware("http")
async def local_guard(request: Request, call_next):
    host = request.headers.get("host", "")
    if urlparse("http://" + host).hostname not in ("127.0.0.1", "localhost"):
        return JSONResponse({"detail": "Jarvis accepts local requests only."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin != "http://" + host:
        return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD") and request.headers.get("x-jarvis-client") != "ui":
        return JSONResponse({"detail": "Missing local client header."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


class Settings(BaseModel):
    display_name: str | None = Field(None, max_length=60)
    setup_complete: bool | None = None
    provider: Literal["ollama", "openai"] | None = None
    model: str | None = Field(None, max_length=200)
    voice: Literal["bm_george", "bm_lewis", "am_adam", "am_michael", "af_heart", "bf_emma"] | None = None
    speed: float | None = Field(None, ge=0.7, le=1.3)
    openai_key: str | None = Field(None, max_length=500)
    google_client_id: str | None = Field(None, max_length=500)
    google_client_secret: str | None = Field(None, max_length=500)
    telegram_token: str | None = Field(None, max_length=500)
    telegram_chat_id: str | None = Field(None, pattern=r"^-?\d*$", max_length=40)
    telegram_gateway: bool | None = None


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class Chat(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)
    provider: Literal["ollama", "openai"]
    model: str = Field(min_length=1, max_length=200)


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=6000)


class Send(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.get("/api/settings")
async def settings():
    c = load()
    return {k: c[k] for k in ("display_name", "setup_complete", "provider", "model", "voice", "speed", "telegram_chat_id", "telegram_gateway", "desktop_voice")} | {"openai_configured": bool(c["openai_key"]), "google_configured": bool(c["google_client_id"]), "telegram_configured": bool(c["telegram_token"])}


@app.get("/api/health")
async def health():
    return {"application": "jarvis-local", "version": "1.1.0", "root": str(ROOT), "pid": os.getpid(), "instance": os.getenv("JARVIS_INSTANCE_ID", ""), "voice": voice.status()}


@app.get("/api/audio/devices")
async def audio_devices():
    import sounddevice as sd
    try:
        devices = await asyncio.to_thread(sd.query_devices)
        return {"devices": [{"name": d["name"], "input": d["max_input_channels"] > 0, "output": d["max_output_channels"] > 0} for d in devices], "default_input": int(sd.default.device[0]), "default_output": int(sd.default.device[1])}
    except Exception:
        raise HTTPException(503, "No audio devices available. Select a default microphone and speaker in operating system sound settings.") from None


@app.post("/api/settings")
async def update_settings(body: Settings):
    values = body.model_dump(exclude_none=True)
    if values.get("openai_key"):
        await services.request_json("GET", "https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + values["openai_key"]})
    if values.get("telegram_token"):
        await services.telegram("getMe", token=values["telegram_token"])
    if values.get("telegram_gateway"):
        c = load() | values
        if not c["telegram_chat_id"] or not c["telegram_token"] or not c["model"]:
            raise HTTPException(409, "Choose a model and configure your Telegram bot and chat ID before enabling replies.")
        await services.telegram("getChat", {"chat_id": c["telegram_chat_id"]}, token=c["telegram_token"])
    save(values)
    if "telegram_token" in values or "telegram_chat_id" in values:
        services.telegram_cache.clear()
        services.telegram_offset = 0
    return await settings()


@app.get("/api/status")
async def status():
    c = load()
    async def ollama():
        try:
            tags = await services.models("ollama")
            return {"connected": True, "models": tags}
        except HTTPException:
            return {"connected": False, "models": [], "detail": "Start Ollama to use local models."}
    async def gmail():
        if not c["google_tokens"]:
            return {"connected": False, "detail": "Authorization required"}
        try:
            p = await services.gmail_profile()
            return {"connected": True, "account": p["emailAddress"]}
        except HTTPException as e:
            return {"connected": False, "detail": e.detail}
    async def tg():
        if not c["telegram_token"]:
            return {"connected": False, "detail": "Bot token required"}
        try:
            p = await services.telegram("getMe")
            paired = False
            if c["telegram_chat_id"]:
                await services.telegram("getChat", {"chat_id": c["telegram_chat_id"]})
                paired = True
            return {"connected": paired, "bot_verified": True, "account": "@" + p.get("username", "bot"), "detail": "Paired" if paired else "Set your chat ID and start the bot", "gateway": c["telegram_gateway"], "error": gateway_error}
        except HTTPException as e:
            return {"connected": False, "detail": e.detail}
    o, g, t = await asyncio.gather(ollama(), gmail(), tg())
    return {"ollama": o, "gmail": g, "telegram": t, "openai": {"configured": bool(c["openai_key"])}, "voice": voice.status()}


@app.get("/api/models/{provider}")
async def get_models(provider: Literal["ollama", "openai"]):
    return {"models": await services.models(provider)}


@app.post("/api/chat")
async def chat(body: Chat):
    context = []
    prompt = body.messages[-1].content.lower()
    if re.search(r"\b(email|emails|gmail|inbox|mail)\b", prompt):
        try:
            context.append("Gmail inbox metadata and snippets: " + json.dumps(await services.gmail_messages()))
        except HTTPException as e:
            context.append("Gmail unavailable: " + str(e.detail))
    if re.search(r"\btelegram\b", prompt):
        try:
            if not load()["telegram_gateway"]:
                await services.telegram_messages()
            context.append("Recent messages sent to your paired Telegram bot: " + json.dumps(services.telegram_cache[-6:]))
        except HTTPException as e:
            context.append("Telegram unavailable: " + str(e.detail))
    text = await services.chat_reply([m.model_dump() for m in body.messages], body.provider, body.model, "\n".join(context))
    return {"text": text, "provider": body.provider, "model": body.model}


async def desktop_reply(history):
    c = load()
    if not c["model"]:
        raise HTTPException(409, "Choose an LLM in the dashboard before using desktop voice.")
    result = await chat(Chat(messages=[Message(role=m["role"], content=m["content"]) for m in history], provider=c["provider"], model=c["model"]))
    return result["text"]


def desktop_dispatch(history):
    return asyncio.run_coroutine_threadsafe(desktop_reply(history), desktop_loop).result(timeout=200)


@app.get("/api/desktop/status")
async def desktop_status():
    return desktop.state()


@app.post("/api/desktop/start")
async def desktop_start():
    try:
        return await asyncio.to_thread(desktop.start, desktop_dispatch)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/desktop/stop")
async def desktop_stop():
    return await asyncio.to_thread(desktop.stop)


@app.post("/api/speech")
async def speech(body: Speech):
    c = load()
    try:
        wav = await asyncio.to_thread(voice.speak, body.text, c["voice"], c["speed"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(503, "Kokoro could not synthesize this response. Check the voice engine.")
    return Response(wav, media_type="audio/wav")


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile):
    data = await audio.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "Audio clip is too long (2 MB maximum).")
    try:
        text = await asyncio.to_thread(voice.transcribe, data)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(400, "Could not decode audio. Record a new clip.")
    return {"text": text}


@app.post("/api/voice/retry")
async def retry_voice():
    if not voice.loading:
        asyncio.create_task(asyncio.to_thread(voice.warmup))
    return voice.status()


@app.post("/api/gmail/connect")
async def connect_gmail():
    return {"url": services.oauth_url()}


@app.get("/api/gmail/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    if error or not code:
        raise HTTPException(400, "Google authorization was cancelled. Start Connect Gmail again.")
    await services.finish_oauth(code, state)
    await services.gmail_profile()
    return HTMLResponse('<!doctype html><html><body style="background:#060d12;color:#79e5ee;font-family:system-ui;padding:60px"><h1>Gmail connected.</h1><p>You can close this tab and return to Jarvis.</p><script>if(window.opener){window.opener.postMessage("gmail-connected","http://127.0.0.1:8000");}window.close();</script></body></html>')


@app.get("/api/gmail/messages")
async def inbox(q: str = "in:inbox"):
    return {"messages": await services.gmail_messages(q[:300])}


@app.post("/api/gmail/disconnect")
async def disconnect():
    save({"google_tokens": {}})
    return {"ok": True}


@app.get("/api/telegram/messages")
async def tg_messages():
    if not load()["telegram_gateway"]:
        await services.telegram_messages()
    return {"messages": services.telegram_cache[-12:]}


@app.post("/api/telegram/send")
async def send_telegram(body: Send):
    c = load()
    if not c["telegram_chat_id"]:
        raise HTTPException(409, "Pair your Telegram chat ID first.")
    result = await services.telegram("sendMessage", {"chat_id": c["telegram_chat_id"], "text": body.text})
    return {"ok": True, "message_id": result["message_id"]}


if (ROOT / "dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
