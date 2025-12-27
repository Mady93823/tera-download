import sqlite3
import logging
import time

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file="cloud.db"):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        """Initialize the database table."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    terabox_id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    title TEXT,
                    timestamp INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    username TEXT,
                    joined_at INTEGER
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    def add_user(self, user_id, first_name, username):
        """Add a new user to the database."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, first_name, username, joined_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, first_name, username, int(time.time())))
            conn.commit()
            conn.close()
            # logger.info(f"User saved: {user_id}") # Optional: Reduce log spam
            return True
        except Exception as e:
            logger.error(f"Error adding user to DB: {e}")
            return False

    def get_all_users(self):
        """Get all user IDs."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            users = [row[0] for row in cursor.fetchall()]
            conn.close()
            return users
        except Exception as e:
            logger.error(f"Error fetching users from DB: {e}")
            return []

    def get_video(self, terabox_id):
        """Retrieve video file_id by terabox_id."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT file_id, title FROM videos WHERE terabox_id = ?', (terabox_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Error fetching video from DB: {e}")
            return None

    def add_video(self, terabox_id, file_id, title):
        """Add a new video mapping to the database."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO videos (terabox_id, file_id, title, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (terabox_id, file_id, title, int(time.time())))
            conn.commit()
            conn.close()
            logger.info(f"Added video to DB: {terabox_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding video to DB: {e}")
            return False

    def delete_video(self, terabox_id):
        """Delete a video mapping from the database."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM videos WHERE terabox_id = ?', (terabox_id,))
            changes = cursor.rowcount
            conn.commit()
            conn.close()
            logger.info(f"Deleted video from DB: {terabox_id} (Rows: {changes})")
            return changes > 0
        except Exception as e:
            logger.error(f"Error deleting video from DB: {e}")
            return False
