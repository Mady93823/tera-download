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

   > **How to get TERABOX_COOKIE**:
   > 1. Login to TeraBox on your browser.
   > 2. Open Developer Tools (F12) -> Application -> Cookies.
   > 3. Find the cookie named `ndus` and copy its value.

5. **Deploy**:
   - Click **Deploy**.
   - Wait for the build to finish.
   - Once "Healthy", your bot is ready!

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

## License
MIT
