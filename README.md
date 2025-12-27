# TeraBox Downloader Bot 🚀

A high-performance Telegram bot to download and stream videos from TeraBox links directly to Telegram.

## Features ✨

- **Fast Downloads**: Optimized for speed with multi-threaded downloading and chunked uploads.
- **Cloud Storage**: Automatically uploads videos to a private channel for instant future access.
- **Seamless Streaming**: Supports direct streaming links if files are too large.
- **User Friendly**: Colorful progress bars for both download and upload.
- **Admin Tools**: Broadcast messages to all users and track user statistics.
- **Smart Caching**: Checks database before downloading to serve instantly if available.

## Setup 🛠️

1. **Clone the repository**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment**:
   Create a `.env` file with the following:
   ```ini
   BOT_TOKEN=your_bot_token
   CLOUD_CHANNEL_ID=-100xxxxxxxxxx  # Channel for video storage
   LOG_CHANNEL_ID=-100xxxxxxxxxx    # Channel for user logs
   ADMIN_ID=123456789               # Your Telegram User ID
   ```

## Admin Commands 👑

These commands are only available to the user with `ADMIN_ID`.

- `/users`: View the total number of users who have started the bot.
- `/broadcast <message>`: Send a message to all users of the bot.
  - Example: `/broadcast Hello everyone! We have a new update.`

## Deployment 🌍

### Local
Run `python bot.py`

### Koyeb / Docker
The project includes a `Dockerfile` and is ready for deployment on platforms like Koyeb.

## Technologies 💻
- Python 3.9
- python-telegram-bot
- yt-dlp
- Flask (Keep-alive)
- SQLite

---
*Made with ❤️ by [Your Name]*
