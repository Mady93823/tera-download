# TeraBox Downloader Bot 🚀

A high-performance Telegram bot to download and stream videos from TeraBox links directly to Telegram.

## Features ✨

- **Fast Downloads**: Optimized for speed with multi-threaded downloading and chunked uploads.
- **Smart Streaming**: Videos are optimized for streaming (FastStart), so you can watch without waiting for full download.
- **Cloud Storage**: Automatically uploads videos to a private channel for instant future access.
- **Direct Stream Links**: Supports direct streaming links if files are too large (>50MB).
- **User Friendly**: Colorful progress bars for both download and upload.
- **Admin Tools**: Broadcast messages to all users and track user statistics.
- **Smart Caching**: Checks MongoDB database before downloading to serve instantly if available.

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
   LOG_CHANNEL_ID=-100xxxxxxxxxx    # Channel for logs
   ADMIN_ID=123456789               # Your Telegram User ID
   MONGO_URL=mongodb+srv://...      # Your MongoDB Connection URL
   COLLECTION_NAME=TERABOX          # Default: TERABOX
   ```

## Admin Commands 👑

These commands are only available to the user with `ADMIN_ID`.

- `/users`: View the total number of users who have started the bot.
- `/broadcast <message>`: Send a message to all users of the bot.
  - Example: `/broadcast Hello everyone! We have a new update.`
- `/del <terabox_id>`: Delete a video from the database.

## Deployment 🌍

### Local
Run `python bot.py`

### Koyeb / Docker
The project includes a `Dockerfile` and is ready for deployment on platforms like Koyeb.
Ensure you set the environment variables in your deployment dashboard.

## Technologies 💻
- Python 3.9
- python-telegram-bot
- yt-dlp (with FFmpeg optimization)
- Flask (Keep-alive)
- MongoDB (pymongo)

---
*Made with ❤️*
