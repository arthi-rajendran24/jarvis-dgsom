# JARVIS

A local voice assistant with a minimal sci-fi HUD, audio-reactive core, OpenAI/Ollama model switching, Gmail inbox summaries, and a private Telegram bot. Every spoken reply uses **Kokoro**; speech recognition uses local **Whisper**.

## Clone, then launch

```sh
git clone https://github.com/arthi-rajendran24/jarvis-dgsom.git
cd jarvis-dgsom
```

| Computer | Launch |
| --- | --- |
| Windows 10 22H2 / Windows 11, x64 | Double-click **Start Jarvis.cmd** |
| macOS 14 or newer, Intel or Apple Silicon | Double-click **Start Jarvis.command** |

If the Mac script is not executable, run `chmod +x "Start Jarvis.command"` in the cloned folder, then `./"Start Jarvis.command"`. Use **Terminal** if macOS asks which app should open it. Keep the checkout in a local, writable folder rather than a network share. Paths with spaces are supported. Git is needed to clone; downloading the GitHub source ZIP and extracting it also works.

The launcher automatically installs missing Python, uv, Node.js, JavaScript/Python dependencies, Kokoro/Whisper models, Ollama, and a small starter LLM. It builds the frontend, starts local services, waits for readiness, and opens [Jarvis](http://127.0.0.1:8000). Compatible existing Node and a responding Ollama installation are reused. No Docker, Homebrew, global Python packages, or administrator access is needed on macOS. Windows may request elevation only if the Microsoft Visual C++ runtime is missing.

Allow several minutes for the first download. Use a computer with **8 GB RAM recommended**, a working microphone/speaker, and **8 GB free disk recommended**; fresh setup refuses to continue below 6 GB. Internet is required for initial installation. CPU inference is supported; available acceleration depends on Ollama, your hardware, and existing drivers. Windows ARM and Linux are not currently supported by these launchers. Large LLMs need more RAM/disk; the installer cannot make every model fit every computer.

On a fresh machine, the starter is `qwen3:0.6b` (~523 MB). It is a small baseline model; choose a larger model or OpenAI for more capable responses. Existing installed chat models are reused, and saved model choices are preserved. Runtime versions/checksums are pinned in `scripts/assets.py` and the bootstrap scripts. Ollama verifies downloaded model-layer digests. Python/JavaScript dependencies are locked in `uv.lock` and `package-lock.json`. Whisper weights are pinned to a Hugging Face revision. See [third-party notices](THIRD_PARTY.md).

## First-run screen

1. Enter your name (optional).
2. Choose an installed Ollama model or add **your own OpenAI API key** in Configure accounts. You can switch models/providers later in the dashboard.
3. Test Kokoro playback. Enable desktop listening and allow microphone access, or skip and type instead.
4. Connect your own Gmail and Telegram accounts, or skip and configure them later.

Each coworker uses their own credentials. The installer cannot generate an API key, grant Google consent, pair a Telegram account, or approve operating-system microphone permissions. Account badges reflect live access checks. OpenAI's badge indicates a verified saved key; its model calls still depend on account access and billing.

## Voice and always-on operation

Say **“Jarvis, tell me the time.”** Or say **“Jarvis”**, wait for the acknowledgment, then ask within 12 seconds. The HUD pulses from actual microphone and Kokoro playback levels. Listening pauses while Jarvis responds to avoid self-activation. English is the recognition default.

- **Desktop listening** uses native audio and stays active when the browser closes. Enable it in the first-run screen or Settings. The preference resumes after backend restart. Select default microphone/speakers in operating-system Sound settings. macOS: Privacy & Security → Microphone → allow Terminal/Python. Windows: Privacy & security → Microphone → enable microphone access and access for desktop apps.
- **Browser voice** runs while the tab remains open; click the microphone and grant browser permission. Audio playback also needs a user gesture. Pause desktop mode before using browser chat/audio. Browser and desktop sessions maintain separate in-memory histories.

Both modes need an **awake computer and a running backend**. Sleep, power-off, and logging out stop listening. Recognition checks local Whisper transcripts for the wake phrase; it is not a dedicated wake-word model. Noise and microphone quality affect accuracy/latency. Test your physical microphone in the intended room. The synthetic CI check verifies synthesis/recognition, not real-room wake accuracy. This app implements voice/chat/inbox/bot features; it does not control your computer, files, calendar, or smart home.

## Start, stop, diagnostics, repair

Run these from the cloned folder. Commands on Windows use Command Prompt (in PowerShell prefix the quoted launcher with `& .\`).

| Action | macOS | Windows Command Prompt |
| --- | --- | --- |
| Launch | `./"Start Jarvis.command"` | `"Start Jarvis.cmd"` |
| Setup without opening UI | `./"Start Jarvis.command" setup` | `"Start Jarvis.cmd" setup` |
| Diagnostics / status | `./"Start Jarvis.command" doctor` | `"Start Jarvis.cmd" doctor` |
| Stop owned services | `./"Start Jarvis.command" stop` | `"Start Jarvis.cmd" stop` |
| Repair dependencies | `./"Start Jarvis.command" repair` | `"Start Jarvis.cmd" repair` |
| Install/select an LLM | `./"Start Jarvis.command" setup --model qwen3:4b` | `"Start Jarvis.cmd" setup --model qwen3:4b` |
| Enable startup at login | `./"Start Jarvis.command" startup enable` | `"Start Jarvis.cmd" startup enable` |
| Disable startup at login | `./"Start Jarvis.command" startup disable` | `"Start Jarvis.cmd" startup disable` |
| Remove installed app dependencies | `./"Start Jarvis.command" uninstall` | `"Start Jarvis.cmd" uninstall` |

Repeat launches reuse installed dependencies and verified downloads. Setup and repair preserve account settings. Stop Jarvis before repair. A second launcher opens the existing instance rather than duplicating it. Port 8000 is fixed because Gmail OAuth uses that callback; an unrelated service on that port produces an actionable error. Stop only terminates processes whose installation/instance identity matches, and leaves externally started Ollama running.

The backend is detached from the launcher, so closing the launch terminal does not stop it. Use **stop** to stop it. Optional login startup creates a current-user Mac LaunchAgent or Windows scheduled task with an interactive login trigger. Enable desktop listening separately. Keep the checkout at its original location; disable startup before moving/deleting it. A login-launched Python process may need its own microphone permission. Neither startup integration runs through sleep or power-off.

Uninstall removes Jarvis-owned dependency/build/cache folders and its login registration. **It preserves credentials, downloaded models, and the small executing bootstrap runtime**, and never removes your external Ollama install/models. For a full removal, run doctor first to note the data location, uninstall, then delete the checkout and that data folder yourself. Account revocation remains available in Google/Telegram/OpenAI account settings.

## Where files live

- Project `.runtime/`: private uv, Python, optional Node/Ollama, non-secret installation/process state.
- Project `.cache/`: dependency and verified archive caches; safe to rebuild.
- macOS data: `~/Library/Application Support/Jarvis`.
- Windows data: `%LOCALAPPDATA%\Jarvis`.
- Original checkouts with `.data/settings.json` continue using their existing `.data` directory.
- `JARVIS_DATA_DIR` overrides the data location (useful for isolated development/CI).

Data holds `settings.json`, `models/`, Jarvis-managed `ollama-models/`, and `logs/`. `doctor` prints the actual paths and secret-free diagnostics. POSIX directories/files are private (0700/0600); Windows uses a current-user NTFS ACL. Credentials are **not encrypted at rest**. Protect your OS account and use disk encryption. Never commit/share settings, OAuth client JSON, tokens, logs, or personal screenshots. All of these generated folders are excluded from Git.

## Gmail

1. Enable Gmail API in your Google Cloud project and configure the OAuth consent screen. In testing mode, add each coworker's Gmail address as a test user, or let them create their own project/client.
2. Create an OAuth client of type **Web application**.
3. Register exactly `http://127.0.0.1:8000/api/gmail/callback` as the authorized redirect URI.
4. Download the client JSON and paste it into Connections → Gmail.
5. Click **Connect Gmail**, authorize in the popup, then **Check connection**.

Connected requires a successful live Gmail profile request. Refresh tokens renew access when allowed by Google; testing-mode or revoked grants may need reconnection. Gmail access is **read-only**. Jarvis summarizes the six latest inbox subjects, sender/date metadata, and snippets when asked about email. It cannot send/delete email, read full attachments, or monitor all mail in the background. Disconnect removes local tokens; revoke authorization in your Google account to revoke server-side access too.

## Telegram

1. Create a dedicated bot with [BotFather](https://t.me/BotFather).
2. Send `/start` to it from your private chat.
3. Enter its token and your numeric private chat ID in Connections. Obtain your chat ID from your own Bot API setup or a trusted Telegram ID bot.
4. Click **Verify & pair**. Connected requires successful `getMe` and `getChat` checks.

Jarvis reads text sent to this bot in the paired chat, rather than your entire personal Telegram history. Recent messages are cached in backend memory. **Send this message** sends the exact text entered in the UI. **Reply to my Telegram messages automatically** explicitly enables remote model replies; it is off by default. Enabling it may answer previously queued messages. Dedicated bots avoid conflicting `getUpdates` pollers. Attachments and Telegram voice notes are outside this implementation.

## Models and privacy

The selector uses live provider model lists and excludes known embedding/audio/image models. Ollama runs locally; OpenAI uses Chat Completions and requires a compatible chat model with access on your account. Add/replace the key in Connections; verification happens before saving. `OPENAI_API_KEY` is also supported for backend environments. Do not put keys into source files. To install another local model, use the setup `--model` command above or your own Ollama CLI.

Voice processing stays local. In OpenAI mode, conversation history and integration snippets you request are sent to OpenAI and incur API charges. Gmail/Telegram need internet even with Ollama. Browser conversations clear on refresh/new session; desktop history clears on backend restart. Fonts currently use Google Fonts with system fallbacks; the app itself and installed local inference can operate without internet.

The backend binds to `127.0.0.1` only. Host/origin checks and a custom client header protect local mutations from cross-site requests. OAuth state is random, expires in ten minutes, and is single-use. Secrets never appear in settings/status responses, and launchers disable access logs to exclude OAuth callback codes. This is a single-user local app; do not expose it to the internet without authentication and HTTPS.

## Troubleshooting

- **Downloads fail:** rerun the launcher. Downloads retry, verify hashes, and replace files atomically. Check free disk, proxies/firewalls, and access to GitHub, nodejs.org, Python download hosts, Hugging Face, and Ollama. Never bypass a checksum error.
- **Windows DLL error:** the setup installs Microsoft's x64 Visual C++ runtime when absent; permit its signed installer if Windows asks. `repair` retries it. GPU drivers are optional and managed separately.
- **No microphone/speaker:** select default devices in Sound settings, allow the app's microphone permission, and try Settings → Test voice. The first-run screen shows the default input and a live meter when native capture is active.
- **Port 8000/11434 busy:** stop the conflicting service. The launcher does not kill unknown processes. An old manually launched Jarvis must be stopped in its original terminal.
- **Model too slow or out of memory:** choose a smaller model or OpenAI. First inference loads model weights and can take longer.
- **Gmail redirect mismatch:** use the exact HTTP loopback callback above and a Web OAuth client. Check Gmail API/test-user consent.
- **Telegram conflict/unauthorized:** use a dedicated bot, correct token, and your private chat ID; send `/start` first.
- **Voice setup unavailable:** retry setup, or Settings → Retry voice setup. `doctor` shows the log/data locations. Share its secret-free report, not raw logs/settings.

## Development and verification

After setup, macOS: `.venv/bin/python -m pytest -q`; Windows: `.venv\Scripts\python.exe -m pytest -q`. Build: `npm run build` if using an installed Node, or use setup to build with Jarvis's private Node. For frontend development run `npm run dev`; Vite proxies `/api` to backend port 8000. Backend: the environment's Python `-m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log`.

The [GitHub Actions workflow](.github/workflows/verify.yml) executes the bootstrap on Windows x64, macOS Apple Silicon, and macOS Intel, installs private runtimes, builds, runs tests, synthesizes and transcribes a known Kokoro phrase, downloads a small Ollama model, starts the real app, calls real chat, checks repeat launch, and stops owned services. Microphone hardware, browser permission dialogs, startup at a real login, and personal Gmail/Telegram/OpenAI credentials require manual acceptance on the target machine.
