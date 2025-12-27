import os
import re
import logging
import time
import asyncio
import urllib.parse
from flask import Flask
from threading import Thread
import yt_dlp
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from db import Database

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
CLOUD_CHANNEL_ID = os.getenv('CLOUD_CHANNEL_ID')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

if not CLOUD_CHANNEL_ID:
    logger.warning("⚠️ CLOUD_CHANNEL_ID is not set in .env! Videos will NOT be uploaded to a channel.")

# Initialize Database
db = Database()

# Regex pattern for TeraBox links
TERABOX_PATTERN = r"https?://(?:www\.)?(?:1024)?terabox[a-z0-9]*\.[a-z]+/(?:s/|wap/share/filelist\?surl=)([a-zA-Z0-9_-]+)"

app = Flask('')

@app.route('/')
def home():
    return "I am alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Helper for progress bar
def get_progress_bar(percentage, length=15):
    """Returns a colorful progress bar."""
    try:
        filled = int(percentage / 100 * length)
        # 🟩 for completed, ⬜️ for empty
        bar = '🟩' * filled + '⬜️' * (length - filled)
        return bar
    except:
        return '⬜️' * length

class ProgressFileReader:
    """Helper to track file upload progress."""
    def __init__(self, filename, callback):
        self._file = open(filename, 'rb')
        self._callback = callback
        self._total_size = os.path.getsize(filename)
        self._read_so_far = 0
        self._last_update_time = 0

    def read(self, size=-1):
        # Read larger chunks for better speed
        if size == -1:
            data = self._file.read()
        else:
            # Buffer size optimization: Read at least 64KB chunks
            read_size = max(size, 64 * 1024)
            data = self._file.read(read_size)
            
        self._read_so_far += len(data)
        
        # Throttle updates to avoid flood wait
        now = time.time()
        if now - self._last_update_time > 3 or self._read_so_far == self._total_size:
            self._last_update_time = now
            self._callback(self._read_so_far, self._total_size)
            
        return data

    def close(self):
        if self._file:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class ProgressHook:
    def __init__(self, bot, chat_id, message_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_update = 0
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def __call__(self, d):
        if d['status'] == 'downloading':
            now = time.time()
            if now - self.last_update > 2:  # Update every 2 seconds
                self.last_update = now
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                eta = d.get('_eta_str', 'N/A')
                
                # Create a simple progress bar
                try:
                    p = float(percent.replace('%', ''))
                    bar = get_progress_bar(p)
                except ValueError:
                    bar = '⬜️' * 15

                text = (
                    f"🎬 <b>Downloading Video...</b>\n\n"
                    f"<b>Progress:</b> {bar} {percent}\n"
                    f"<b>Speed:</b> {speed} 🚀\n"
                    f"<b>ETA:</b> {eta} ⏳"
                )
                
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=self.message_id,
                            text=text,
                            parse_mode='HTML'
                        ),
                        self.loop
                    )

def get_iteraplay_video_info(terabox_url):
    """
    Extracts the video info (url, title, thumbnail) using the iteraplay.com API.
    """
    try:
        encoded_url = urllib.parse.quote(terabox_url)
        iteraplay_play_url = f"https://iteraplay.com/api/play.php?url={encoded_url}&key=iTeraPlay2025"
        iteraplay_stream_url = "https://iteraplay.com/api/stream.php"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': iteraplay_play_url,
            'Origin': 'https://iteraplay.com',
            'Content-Type': 'application/json'
        }

        session = requests.Session()
        
        # Step 1: Get play page to set cookies
        logger.info(f"Fetching play page: {iteraplay_play_url}")
        session.get(iteraplay_play_url, headers=headers)
        
        # Step 2: Post to stream API
        logger.info("Posting to stream API...")
        payload = {"url": terabox_url}
        response = session.post(iteraplay_stream_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if 'list' in data and len(data['list']) > 0:
                file_info = data['list'][0]
                
                result = {
                    'title': file_info.get('name') or file_info.get('server_filename', 'TeraBox Video'),
                    'thumbnail': file_info.get('thumbnail', None),
                    'url': None
                }

                if 'fast_stream_url' in file_info:
                    streams = file_info['fast_stream_url']
                    if isinstance(streams, dict):
                        # Prioritize quality
                        for quality in ['1080p', '720p', '480p', '360p']:
                            if quality in streams:
                                result['url'] = streams[quality]
                                break
                        if not result['url']:
                            result['url'] = list(streams.values())[0]
                    else:
                        result['url'] = streams # It might be a string directly
                
                if result['url']:
                    return result

            logger.error(f"No video found in API response: {data}")
        else:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"Error extracting iteraplay URL: {e}")
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Save user to DB
    is_new_user = db.add_user(user.id, user.first_name, user.username)
    
    if is_new_user and LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=(
                    f"🆕 <b>New User Started Bot!</b>\n\n"
                    f"👤 <b>Name:</b> {user.full_name}\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"🔗 <b>Username:</b> @{user.username if user.username else 'None'}"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send log: {e}")

    await update.message.reply_html(
        rf"""👋 Hi {user.mention_html()}!

I can help you convert <b>TeraBox</b> links to direct video links!

<b>How to use:</b>
Just send me a TeraBox link like:
<code>https://1024terabox.com/s/1jggGfxx...</code>

I will fetch the video and send it to you! 🚀"""
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "ℹ️ <b>How to use:</b>\n\n"
        "1. Copy a TeraBox link (e.g., <code>https://1024terabox.com/s/...</code>)\n"
        "2. Paste it here.\n"
        "3. Wait for the magic! ✨\n\n"
        "<i>Note: Large files (>50MB) will be sent as a direct stream link due to Telegram limits.</i>"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def download_video(url, output_template, progress_hook):
    """Runs yt-dlp in a separate thread to avoid blocking asyncio loop."""
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'http_headers': {
            'Referer': 'https://iteraplay.com/',
            'Origin': 'https://iteraplay.com',
        },
        'progress_hooks': [progress_hook],
        'socket_timeout': 30,  # Increase timeout
        'retries': 10,        # Retry on 5xx or timeout
        'fragment_retries': 10,
        # Speed optimizations
        'concurrent_fragment_downloads': 5, # Download multiple fragments in parallel
        'buffersize': 1024 * 1024, # 1MB buffer
        'http_chunk_size': 10485760, # 10MB chunks
    }
    
    loop = asyncio.get_running_loop()
    
    def run_yt_dlp():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info

    return await loop.run_in_executor(None, run_yt_dlp)

# Admin Commands
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    users = db.get_all_users()
    await update.message.reply_text(f"📊 <b>Total Users:</b> {len(users)}", parse_mode='HTML')

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    message = update.message.text.split(' ', 1)
    if len(message) < 2:
        await update.message.reply_text("⚠️ <b>Usage:</b> /broadcast <message>", parse_mode='HTML')
        return

    broadcast_msg = message[1]
    users = db.get_all_users()
    sent_count = 0

    status_msg = await update.message.reply_text(f"📣 <b>Broadcasting to {len(users)} users...</b>", parse_mode='HTML')

    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_msg, parse_mode='HTML')
            sent_count += 1
            await asyncio.sleep(0.1) # Avoid flood limits
        except Exception:
            pass
    
    await context.bot.edit_message_text(
        chat_id=user.id,
        message_id=status_msg.message_id,
        text=f"✅ <b>Broadcast Complete!</b>\n\nSent to {sent_count}/{len(users)} users.",
        parse_mode='HTML'
    )

async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    message = update.message.text.split(' ', 1)
    if len(message) < 2:
        await update.message.reply_text("⚠️ <b>Usage:</b> /del <terabox_id>", parse_mode='HTML')
        return

    terabox_id = message[1].strip()
    
    # Check if ID starts with '1', if user forgot it but provided the rest
    # (Though we shouldn't guess too much for deletion to be safe, exact match is better)
    
    if db.delete_video(terabox_id):
        await update.message.reply_text(f"✅ <b>Deleted:</b> <code>{terabox_id}</code> from database.", parse_mode='HTML')
    else:
        await update.message.reply_text(f"❌ <b>Not Found:</b> <code>{terabox_id}</code> in database.", parse_mode='HTML')

async def handle_terabox_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    text = message.text
    user = update.effective_user
    
    # Save user to DB on interaction
    db.add_user(user.id, user.first_name, user.username)

    # Check for TeraBox link
    match = re.search(TERABOX_PATTERN, text)
    if not match:
        await message.reply_text("❌ <b>Invalid Link</b>\nPlease send a valid TeraBox link.", parse_mode='HTML')
        return

    terabox_url = match.group(0) # Use the full matched URL
    file_id = match.group(1)
    
    # Normalize ID for 'surl' links (usually need '1' prefix)
    if "surl=" in terabox_url and not file_id.startswith("1"):
        file_id = "1" + file_id
        # Reconstruct standard URL for consistency
        terabox_url = f"https://terabox.com/s/{file_id}"
    
    # Check if video exists in DB
    cached_video = db.get_video(file_id)
    if cached_video:
        telegram_file_id, cached_title = cached_video
        logger.info(f"Video found in cache: {file_id}")
        
        try:
            # Send cached video
            await message.reply_video(
                video=telegram_file_id, 
                caption=f"🎬 <b>{cached_title}</b>\n\n⚡️ <i>Fast delivered from Cloud</i>", 
                parse_mode='HTML'
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send cached video (might be deleted): {e}")
            # If failed, proceed to download again
            pass

    # Initial status message
    status_msg = await message.reply_text(f"🔍 <b>Analyzing Link...</b>\nPlease wait a moment.", parse_mode='HTML')

    # Get video info from iteraplay
    video_info = get_iteraplay_video_info(terabox_url)
    
    if not video_info or not video_info['url']:
        await context.bot.edit_message_text(chat_id=message.chat_id, message_id=status_msg.message_id, 
                                            text="❌ <b>Error:</b> Failed to extract video.\nThe link might be invalid or expired.", parse_mode='HTML')
        return

    direct_url = video_info['url']
    video_title = video_info['title']
    thumbnail_url = video_info['thumbnail']

    # Update status with video details
    info_text = (
        f"🎬 <b>Found Video!</b>\n"
        f"<b>Title:</b> {video_title}\n"
        f"⬇️ Starting download..."
    )
    
    # If thumbnail exists, we might want to delete text message and send photo, 
    # but editing text is smoother for progress. We'll stick to text edit for progress.
    await context.bot.edit_message_text(chat_id=message.chat_id, message_id=status_msg.message_id, 
                                        text=info_text, parse_mode='HTML')

    # Download with yt-dlp
    output_template = f"downloads/{file_id}.%(ext)s"
    
    # Initialize Progress Hook
    progress_hook = ProgressHook(context.bot, message.chat_id, status_msg.message_id)

    filename = None
    try:
        # Run download in executor
        filename, info = await download_video(direct_url, output_template, progress_hook)
            
        await context.bot.edit_message_text(chat_id=message.chat_id, message_id=status_msg.message_id, 
                                            text="✅ <b>Download Complete!</b>\n\n📤 Uploading to Telegram...", parse_mode='HTML')
        
        # Check file size (Telegram bot limit 50MB)
        file_size = os.path.getsize(filename)
        if file_size > 50 * 1024 * 1024:
            await message.reply_text(
                f"⚠️ <b>File too large for Telegram!</b> ({file_size/1024/1024:.2f} MB)\n\n"
                f"🔗 <b>Direct Stream Link:</b>\n{direct_url}", 
                parse_mode='HTML'
            )
        else:
            caption = f"🎬 <b>{video_title}</b>"
            
            # Helper to update upload progress
            def upload_progress_callback(current, total):
                try:
                    percent = (current / total) * 100
                    bar = get_progress_bar(percent)
                    text = (
                        f"📤 <b>Uploading Video...</b>\n\n"
                        f"<b>Progress:</b> {bar} {percent:.1f}%\n"
                    )
                    # We need to run this in the event loop
                    asyncio.run_coroutine_threadsafe(
                        context.bot.edit_message_text(
                            chat_id=message.chat_id,
                            message_id=status_msg.message_id,
                            text=text,
                            parse_mode='HTML'
                        ),
                        asyncio.get_running_loop()
                    )
                except Exception:
                    pass # Ignore errors during UI update

            # 1. Send to Cloud Channel (if configured)
            sent_to_cloud = False
            telegram_file_id = None
            
            if CLOUD_CHANNEL_ID:
                try:
                    logger.info(f"Uploading to Cloud Channel: {CLOUD_CHANNEL_ID}")
                    
                    # Use ProgressFileReader
                    with ProgressFileReader(filename, upload_progress_callback) as video_file:
                        # Note: We pass the wrapper object as the video
                        # python-telegram-bot's input_file accepts read() method
                        cloud_msg = await context.bot.send_video(
                            chat_id=CLOUD_CHANNEL_ID,
                            video=video_file, # This works because it has read()
                            caption=(
                                f"🆔: {file_id}\n"
                                f"🎬: {video_title}\n\n"
                                f"👤 <b>Requested by:</b> {user.mention_html()}\n"
                                f"🆔 <b>User ID:</b> <code>{user.id}</code>"
                            ),
                            parse_mode='HTML',
                            read_timeout=300, 
                            write_timeout=300
                        )
                        if cloud_msg.video:
                            telegram_file_id = cloud_msg.video.file_id
                            sent_to_cloud = True
                            
                            # Save to DB
                            db.add_video(file_id, telegram_file_id, video_title)
                except Exception as e:
                    logger.error(f"Failed to upload to Cloud Channel: {e}")

            # 2. Send to User
            if sent_to_cloud and telegram_file_id:
                # Forward/Send using file_id (Fast!)
                await message.reply_video(
                    video=telegram_file_id,
                    caption=caption,
                    parse_mode='HTML'
                )
            else:
                # Upload directly to user (if cloud failed or not configured)
                # We reuse the ProgressFileReader if we haven't uploaded yet, 
                # but if we failed above, we need a fresh reader.
                try:
                    with ProgressFileReader(filename, upload_progress_callback) as video_file:
                        user_msg = await message.reply_video(
                            video=video_file, 
                            caption=caption, 
                            parse_mode='HTML',
                            read_timeout=300,
                            write_timeout=300
                        )
                        
                        # Opportunistic: If we uploaded to user, try to save that file_id to DB too?
                        if not sent_to_cloud and user_msg.video:
                            db.add_video(file_id, user_msg.video.file_id, video_title)
                except Exception as e:
                     logger.error(f"Failed to upload to user: {e}")
                     await message.reply_text("❌ Failed to upload video.")

        
        # Cleanup is handled in finally block

    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await message.reply_text(f"❌ <b>Error processing video:</b> {str(e)}", parse_mode='HTML')
    finally:
        # Cleanup
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
                logger.info(f"Deleted file: {filename}")
            except Exception as e:
                logger.error(f"Failed to delete file {filename}: {e}")
        
        try:
            await context.bot.delete_message(chat_id=message.chat_id, message_id=status_msg.message_id)
        except:
            pass

def main() -> None:
    """Start the bot."""
    if not TOKEN:
        print("Error: BOT_TOKEN not set.")
        return

    # Create the Application and pass it your bot's token.
    # Increase timeouts for large file uploads
    application = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(300)   # 5 minutes
        .write_timeout(300)  # 5 minutes
        .connect_timeout(60) # 1 minute
        .pool_timeout(300)   # 5 minutes
        .build()
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("del", admin_delete))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terabox_link))

    # Run the bot
    print("Bot is running...")
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Ensure downloads directory exists
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    main()
