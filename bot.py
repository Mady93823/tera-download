import os
import re
import logging
import time
import asyncio
import urllib.parse
import subprocess
import tempfile
from http.cookies import SimpleCookie
from flask import Flask, send_from_directory
from threading import Thread
import yt_dlp
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from db import Database
from TeraboxDL import TeraboxDL

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Suppress httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
CLOUD_CHANNEL_ID = os.getenv('CLOUD_CHANNEL_ID')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
TERABOX_COOKIE = os.getenv('TERABOX_COOKIE')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
ENABLE_WEB_SERVER = os.getenv('ENABLE_WEB_SERVER', 'true').lower() == 'true'
TELEGRAM_API_URL = os.getenv('TELEGRAM_API_URL') # Optional: Custom Bot API URL

if not CLOUD_CHANNEL_ID:
    logger.warning("⚠️ CLOUD_CHANNEL_ID is not set in .env! Videos will NOT be uploaded to a channel.")

if not TERABOX_COOKIE:
    logger.warning("⚠️ TERABOX_COOKIE is not set in .env! Downloading might fail.")

# Initialize Database
db = Database()

# Concurrency Control
MAX_CONCURRENT_DOWNLOADS = 2
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# Regex pattern for TeraBox links
TERABOX_PATTERN = r"https?://(?:www\.)?(?:1024tera|1024terabox|terabox|teraboxapp|teraboxshare|mirrobox|nephobox|freeterabox|4funbox|momerybox|tibibox|terasharelink)\.com/(?:s/|wap/share/filelist\?surl=|sharing/link\?surl=)([a-zA-Z0-9_-]+)"

app = Flask('')

@app.route('/')
def home():
    return "I am alive"

@app.route('/watch/<path:filename>')
def stream_video(filename):
    # Enable Range requests for streaming
    return send_from_directory('downloads', filename)

def run():
    app.run(host='0.0.0.0', port=8000)

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
        if now - self._last_update_time > 5 or self._read_so_far == self._total_size:
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

# Dictionary to store active downloads for cancellation
# Format: {user_id: {"process": subprocess_object, "cancelled": boolean, "task": asyncio_task}}
active_downloads = {}

async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("cancel_"):
        return
        
    user_id = int(data.split("_")[1])
    
    # Verify if the user clicking is the one who initiated
    if update.effective_user.id != user_id:
        await query.answer("❌ You cannot cancel this download.", show_alert=True)
        return

    if user_id in active_downloads:
        active_downloads[user_id]["cancelled"] = True
        await query.edit_message_text("🚫 <b>Download Cancelled by User.</b>", parse_mode='HTML')
        # The download function checks this flag and stops
    else:
        await query.edit_message_text("⚠️ <b>Download already finished or not found.</b>", parse_mode='HTML')
class ProgressHook:
    def __init__(self, bot, chat_id, message_id, user_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.user_id = user_id
        self.last_update = 0
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def __call__(self, d):
        # Check for cancellation
        if self.user_id in active_downloads and active_downloads[self.user_id].get("cancelled", False):
            raise yt_dlp.utils.DownloadError("Download cancelled by user")

        if d['status'] == 'downloading':
            now = time.time()
            if now - self.last_update > 5:  # Update every 5 seconds (Optimized)
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
                
                # Cancel Button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{self.user_id}")]
                ])

                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=self.message_id,
                            text=text,
                            parse_mode='HTML',
                            reply_markup=keyboard
                        ),
                        self.loop
                    )

def get_progress_bar(percent):
    """Generates a visual progress bar."""
    bar_len = 15
    filled_len = int(bar_len * percent / 100)
    bar = '⬛️' * filled_len + '⬜️' * (bar_len - filled_len)
    return bar

def transcode_to_target_size(input_path, target_mb, duration, width=None, height=None):
    try:
        target_bits = int(target_mb * 1024 * 1024 * 8)
        if not duration or duration <= 0:
            duration = 600
        total_bitrate = max(int(target_bits / duration), 300000)
        audio_bitrate = 96000
        video_bitrate = max(total_bitrate - audio_bitrate, 200000)
        output_path = os.path.splitext(input_path)[0] + ".compressed.mp4"
        vf = None
        if width and height:
            vf = "scale='min(1280,iw)':min(720,ih):force_original_aspect_ratio=decrease"
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-preset', 'veryfast',
            '-b:v', str(video_bitrate), '-maxrate', str(video_bitrate), '-bufsize', str(video_bitrate * 2),
            '-c:a', 'aac', '-b:a', str(audio_bitrate),
            '-movflags', '+faststart'
        ]
        if vf:
            cmd.extend(['-vf', vf])
        cmd.append(output_path)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            try:
                logger.error(result.stderr.decode())
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Transcode error: {e}")
    return None
def get_video_info(terabox_url):
    """
    Extracts the video info (url, title, thumbnail) using terabox-downloader.
    """
    if not TERABOX_COOKIE:
        logger.error("TERABOX_COOKIE not set.")
        return None

    try:
        terabox = TeraboxDL(TERABOX_COOKIE)
        file_info = terabox.get_file_info(terabox_url)
        
        if "error" in file_info:
            logger.error(f"TeraboxDL error: {file_info['error']}")
            return None
            
        result = {
            'title': file_info.get('file_name', 'TeraBox Video'),
            'thumbnail': file_info.get('thumbnail', None),
            'url': file_info.get('download_link', None)
        }
        
        if result['url']:
            return result
            
    except Exception as e:
        logger.error(f"Error extracting video info: {e}")
    
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
Just send me a TeraBox link :

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
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'progress_hooks': [progress_hook],
        'socket_timeout': 120,  # Increase timeout
        'retries': 20,        # Retry on 5xx or timeout
        'fragment_retries': 20,
        # Speed optimizations
        'concurrent_fragment_downloads': 5, # Download multiple fragments in parallel
        'buffersize': 1024 * 1024, # 1MB buffer
        'http_chunk_size': 10485760, # 10MB chunks
        # Aria2c Integration for faster downloads
        'external_downloader': 'aria2c',
        'external_downloader_args': [
            '-x', '16', # 16 connections
            '-s', '16', # 16 split
            '-k', '1M', # 1MB min split
            '--check-certificate=false'
        ],
        # FFmpeg Post-processing for FastStart (Move moov atom to front)
        'postprocessor_args': {
            'ffmpeg': ['-movflags', '+faststart']
        },
    }
    
    # Handle Cookies safely (Fix: Write to Netscape format file)
    cookie_file_path = None
    if TERABOX_COOKIE:
        try:
            # Create temp cookie file
            fd, cookie_file_path = tempfile.mkstemp(suffix='.txt', text=True)
            with os.fdopen(fd, 'w') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file is generated by the bot.\n\n")
                
                # Parse the cookie string
                cookie = SimpleCookie()
                cookie.load(TERABOX_COOKIE)
                
                for key, morsel in cookie.items():
                    # domain flag path secure expiration name value
                    f.write(f".terabox.com\tTRUE\t/\tFALSE\t2147483647\t{key}\t{morsel.value}\n")
            
            ydl_opts['cookiefile'] = cookie_file_path
        except Exception as e:
            logger.error(f"Failed to create cookie file: {e}")
            # Fallback to header (will show warning but work)
            ydl_opts['http_headers'] = {'Cookie': TERABOX_COOKIE}
    
    loop = asyncio.get_running_loop()
    
    def run_yt_dlp():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Manual FastStart (Force moov atom to front)
                try:
                    if filename.endswith('.mp4'):
                        faststart_filename = filename + ".temp.mp4"
                        logger.info(f"Running FastStart on {filename}...")
                        
                        # Run ffmpeg command
                        result = subprocess.run(
                            ['ffmpeg', '-y', '-i', filename, '-c', 'copy', '-movflags', '+faststart', faststart_filename],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        
                        if result.returncode == 0 and os.path.exists(faststart_filename):
                            os.replace(faststart_filename, filename)
                            logger.info("FastStart complete.")
                        else:
                            logger.error(f"FastStart failed: {result.stderr.decode()}")
                except Exception as e:
                    logger.error(f"FastStart exception: {e}")

                return filename, info
        finally:
            # Cleanup cookie file
            if cookie_file_path and os.path.exists(cookie_file_path):
                try:
                    os.remove(cookie_file_path)
                except:
                    pass

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

async def admin_set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dynamically update the TeraBox cookie."""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    message = update.message.text.split(' ', 1)
    if len(message) < 2:
        await update.message.reply_text("⚠️ <b>Usage:</b> /setcookie <new_cookie_value>", parse_mode='HTML')
        return

    new_cookie = message[1].strip()
    
    # Update global variable
    global TERABOX_COOKIE
    TERABOX_COOKIE = new_cookie
    
    await update.message.reply_text("✅ <b>Cookie Updated!</b>\n\nNote: This change is temporary and will reset on restart unless you update .env file.", parse_mode='HTML')

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
    
    # Normalize ID for 'surl' links (usually need '1' prefix if missing)
    if "surl=" in terabox_url and not file_id.startswith("1"):
        file_id = "1" + file_id
        
    # FORCE normalize to terabox.com to ensure downloader compatibility
    # Many domains (teraboxshare, 1024tera, etc.) share the same ID structure
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

    # Get video info
    video_info = get_video_info(terabox_url)
    
    if not video_info or not video_info['url']:
        await context.bot.edit_message_text(chat_id=message.chat_id, message_id=status_msg.message_id, 
                                            text="❌ <b>Error:</b> Failed to extract video.\nThe link might be invalid or expired.", parse_mode='HTML')
        return

    direct_url = video_info['url']
    # Escape title to prevent HTML parse errors
    video_title = video_info['title'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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

    # Check for concurrency limit
    if download_semaphore.locked():
        await context.bot.edit_message_text(
            chat_id=message.chat_id, 
            message_id=status_msg.message_id,
            text=f"{info_text}\n\n⏳ <b>Queue is full.</b> Waiting for a slot...",
            parse_mode='HTML'
        )

    async with download_semaphore:
        # Update status once slot is acquired
        await context.bot.edit_message_text(
            chat_id=message.chat_id,
            message_id=status_msg.message_id,
            text=f"{info_text}\n\n⬇️ <b>Starting download...</b>",
            parse_mode='HTML'
        )

        # Download with yt-dlp
        output_template = f"downloads/{file_id}.%(ext)s"
        
        # Initialize Progress Hook
        progress_hook = ProgressHook(context.bot, message.chat_id, status_msg.message_id, user.id)

        filename = None
        thumb_path = None
        should_delete_immediately = True # Flag to control deletion

        # Register download for cancellation
        active_downloads[user.id] = {"cancelled": False}

        try:
            # Run download in executor
            filename, info = await download_video(direct_url, output_template, progress_hook)
            
            # Extract metadata
            width = info.get('width')
            height = info.get('height')
            duration = info.get('duration')
            thumbnail_url = info.get('thumbnail')
            
            # Download thumbnail
            if thumbnail_url:
                try:
                    thumb_resp = requests.get(thumbnail_url)
                    if thumb_resp.status_code == 200:
                        thumb_path = f"{filename}.jpg"
                        with open(thumb_path, 'wb') as f:
                            f.write(thumb_resp.content)
                except Exception as e:
                    logger.error(f"Failed to download thumbnail: {e}")
                
            await context.bot.edit_message_text(chat_id=message.chat_id, message_id=status_msg.message_id, 
                                                text="✅ <b>Download Complete!</b>\n\n📤 Uploading to Telegram...", parse_mode='HTML')
            
            file_size = os.path.getsize(filename)
            # 50MB for normal bot, 2000MB (2GB) for local API server
            upload_limit = 2000 * 1024 * 1024 if TELEGRAM_API_URL else 50 * 1024 * 1024
            
            if file_size > upload_limit:
                if ENABLE_WEB_SERVER:
                    file_basename = os.path.basename(filename)
                    stream_link = f"{BASE_URL}/watch/{file_basename}"
                    await message.reply_text(
                        f"⚠️ <b>File too large for Telegram!</b> ({file_size/1024/1024:.2f} MB)\n\n"
                        f"🔗 <b>Stream/Download Link:</b>\n{stream_link}\n\n"
                        f"<i>Link expires in 30 minutes.</i>",
                        parse_mode='HTML'
                    )
                    should_delete_immediately = False
                    
                    # Schedule deletion
                    async def delete_later(f_path, delay):
                        await asyncio.sleep(delay)
                        try:
                            if os.path.exists(f_path):
                                os.remove(f_path)
                                logger.info(f"Deleted expired file: {f_path}")
                        except Exception as e:
                            logger.error(f"Error deleting expired file {f_path}: {e}")

                    # Run deletion task in background (30 mins = 1800 sec)
                    asyncio.create_task(delete_later(filename, 1800))
                else:
                    # Fallback if server disabled: Try to transcode?
                    # But 2GB is too big to transcode quickly.
                    await message.reply_text(
                        f"⚠️ <b>File too large ({file_size/1024/1024:.2f} MB)</b> and Web Server is disabled.\n"
                        f"Cannot send file.",
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
                            
                            thumb_file = open(thumb_path, 'rb') if thumb_path else None
                            try:
                                cloud_msg = await context.bot.send_video(
                                    chat_id=CLOUD_CHANNEL_ID,
                                    video=video_file, # This works because it has read()
                                    caption=(
                                        f"🆔 <code>{file_id}</code>\n"
                                        f"🎬: {video_title}\n\n"
                                        f"👤 <b>Requested by:</b> {user.mention_html()}\n"
                                        f"🆔 <b>User ID:</b> <code>{user.id}</code>"
                                    ),
                                    parse_mode='HTML',
                                    read_timeout=300, 
                                    write_timeout=300,
                                    width=width,
                                    height=height,
                                    duration=duration,
                                    supports_streaming=True,
                                    thumbnail=thumb_file
                                )
                            finally:
                                if thumb_file:
                                    thumb_file.close()

                            if cloud_msg.video:
                                telegram_file_id = cloud_msg.video.file_id
                                sent_to_cloud = True
                                
                                # Save to DB
                                db.add_video(file_id, telegram_file_id, video_title)
                    except Exception as e:
                        logger.error(f"Failed to upload to Cloud Channel: {e}")

                # Send log to LOG_CHANNEL_ID
                if LOG_CHANNEL_ID and telegram_file_id:
                    try:
                        await context.bot.send_message(
                            chat_id=LOG_CHANNEL_ID,
                            text=(
                                f"📝 <b>New Video Processed!</b>\n\n"
                                f"🎬 <b>Title:</b> {video_title}\n"
                                f"🆔 <b>TeraBox ID:</b> <code>{file_id}</code>\n"
                                f"👤 <b>User:</b> {user.mention_html()} (<code>{user.id}</code>)\n"
                                f"💾 <b>File ID:</b> <code>{telegram_file_id}</code>"
                            ),
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Failed to send log to LOG_CHANNEL: {e}")

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
                            thumb_file = open(thumb_path, 'rb') if thumb_path else None
                            try:
                                user_msg = await message.reply_video(
                                    video=video_file, 
                                    caption=caption, 
                                    parse_mode='HTML',
                                    read_timeout=300,
                                    write_timeout=300,
                                    width=width,
                                    height=height,
                                    duration=duration,
                                    supports_streaming=True,
                                    thumbnail=thumb_file
                                )
                            finally:
                                if thumb_file:
                                    thumb_file.close()
                            
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
            if should_delete_immediately and filename and os.path.exists(filename):
                try:
                    os.remove(filename)
                    logger.info(f"Deleted file: {filename}")
                except Exception as e:
                    logger.error(f"Failed to delete file {filename}: {e}")
            
            # Cleanup thumbnail
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass

            try:
                await context.bot.delete_message(chat_id=message.chat_id, message_id=status_msg.message_id)
            except:
                pass

def clean_downloads():
    """Clean the downloads directory on startup."""
    if os.path.exists("downloads"):
        try:
            import shutil
            shutil.rmtree("downloads")
            os.makedirs("downloads")
            logger.info("Cleaned downloads directory.")
        except Exception as e:
            logger.error(f"Failed to clean downloads directory: {e}")

def main() -> None:
    """Start the bot."""
    if not TOKEN:
        print("Error: BOT_TOKEN not set.")
        return

    # Clean downloads on startup
    clean_downloads()

    # Create the Application and pass it your bot's token.
    # Increase timeouts for large file uploads
    builder = Application.builder().token(TOKEN)
    
    if TELEGRAM_API_URL:
        logger.info(f"Using Custom Bot API Server: {TELEGRAM_API_URL}")
        builder.base_url(TELEGRAM_API_URL)
        builder.base_file_url(f"{TELEGRAM_API_URL}/file/bot")

    application = (
        builder
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
    application.add_handler(CommandHandler("setcookie", admin_set_cookie))
    application.add_handler(CallbackQueryHandler(cancel_download, pattern="^cancel_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terabox_link))

    # Run the bot
    print("Bot is running...")
    if ENABLE_WEB_SERVER:
        keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Ensure downloads directory exists
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    main()
