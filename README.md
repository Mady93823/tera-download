# TeraBox Downloader Telegram Bot

A high-performance Telegram bot that downloads videos from various TeraBox domains, optimizes them for streaming, and uploads them to Telegram.

## Features
- 🚀 **Multi-Domain Support**: Works with `terabox.com`, `teraboxapp.com`, `1024tera.com`, and many more.
- 📱 **Streaming Optimized**: Automatically converts videos to `FastStart` (moov atom at front) for instant playback on mobile devices without full downloading.
- 📺 **Direct Stream Link**: Generates a direct stream link for large files (>50MB) that exceeds Telegram's bot upload limit.
- ⚡ **High Speed**: Uses `yt-dlp` with multi-threaded downloading.
- 🍪 **Cookie Support**: Bypasses login restrictions using cookies.
- ☁️ **Cloud Channel**: Optionally uploads to a private channel for storage.
- 📊 **Admin Dashboard**: View user stats and broadcast messages.

## Admin Commands
The following commands are available only to the admin (specified by `ADMIN_ID`):

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/users` | `/users` | Shows total number of bot users. |
| `/broadcast` | `/broadcast <message>` | Sends a message to all users. |
| `/del` | `/del <terabox_id>` | Deletes a video from the database cache. |
| `/setcookie` | `/setcookie <ndus_value>` | Updates the TeraBox cookie instantly without restart. |

## Deployment on Koyeb

1. **Fork/Clone this repository.**

2. **Create a Koyeb Account** at [koyeb.com](https://www.koyeb.com/).

3. **Create a New App**:
   - Select **GitHub** as the deployment method.
   - Choose this repository.

4. **Configure Environment Variables**:
   In the **Settings** -> **Environment Variables** section, add the following:

   | Variable | Description |
   | :--- | :--- |
   | `BOT_TOKEN` | Your Telegram Bot Token from @BotFather. |
   | `API_ID` | Your Telegram API ID (optional/if used). |
   | `API_HASH` | Your Telegram API Hash (optional/if used). |
   | `ADMIN_ID` | Your Telegram User ID (get it from @userinfobot). |
   | `CLOUD_CHANNEL_ID` | (Optional) Channel ID to forward videos to (e.g., `-100xxxx`). |
   | `LOG_CHANNEL_ID` | (Optional) Channel ID for logs. |
   | `TERABOX_COOKIE` | **Required**. Your `ndus` cookie from TeraBox. |
   | `BASE_URL` | **Required**. Your Koyeb App Public URL (e.g., `https://my-app.koyeb.app`). |
   | `ENABLE_WEB_SERVER` | (Optional) Set to `false` if deploying on VPS without public ports (default: `true`). |
   | `TELEGRAM_API_URL` | (Optional) Custom Bot API URL for large uploads (up to 2GB). E.g., `http://localhost:8081/bot`. |

   > **How to get TERABOX_COOKIE**:
   > 1. Login to TeraBox on your browser.
   > 2. Open Developer Tools (F12) -> Application -> Cookies.
   > 3. Find the cookie named `ndus` and copy its value.

5. **Deploy**:
   - Click **Deploy**.
   - Wait for the build to finish.
   - Once "Healthy", your bot is ready!

## Handling Large Files (Up to 2GB)
Telegram's default bot API limit is **50MB**. To upload files up to **2GB**, you must use a **Local Telegram Bot API Server**.

1. **Install Telegram Bot API Server**:
   Follow instructions [here](https://github.com/tdlib/telegram-bot-api).
   
   Example (Docker):
   ```bash
   docker run -d -p 8081:8081 --name=telegram-bot-api \
       -e TELEGRAM_API_ID=<your_api_id> \
       -e TELEGRAM_API_HASH=<your_api_hash> \
       aiogram/telegram-bot-api:latest
   ```

2. **Configure Environment Variable**:
   Set `TELEGRAM_API_URL` in your `.env` file:
   ```env
   TELEGRAM_API_URL=http://localhost:8081/bot
   ```
   *(Replace localhost with your server IP if running separately)*

## Local Development

1. Clone the repo:
   ```bash
   git clone https://github.com/yourusername/tera-bot.git
   cd tera-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Setup `.env` file (see `.env.example`).

4. Run the bot:
   ```bash
   python bot.py
   ```

## Requirements
- Python 3.9+
- FFmpeg (installed on the system)
- Aria2c (recommended for faster downloads)

## VPS Limitations (LXC/No Public Ports)
If you are running this bot on a **LXC VPS** or a server **without public ports** (e.g., NAT VPS):
1. **Set `ENABLE_WEB_SERVER=false`** in your `.env` file. This prevents the bot from crashing due to port binding errors.
2. **Stream Links will NOT work** because they require a public IP/Port.
3. **Large Files (>50MB)**:
   - If `TELEGRAM_API_URL` is configured (requires local API server), files up to 2GB will upload directly.
   - If NOT configured, the bot will attempt to **transcode** (compress) the video to <50MB. This is CPU intensive and may fail for very large files.

## License
MIT
