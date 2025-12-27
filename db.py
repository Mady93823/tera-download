import os
import logging
import time
import pymongo
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.mongo_url = os.getenv("MONGO_URL")
        self.collection_name = os.getenv("COLLECTION_NAME", "TERABOX")
        self.client = None
        self.db = None
        self.init_db()

    def init_db(self):
        """Initialize the MongoDB connection."""
        try:
            if not self.mongo_url:
                logger.error("MONGO_URL not found in environment variables.")
                return

            self.client = pymongo.MongoClient(self.mongo_url)
            self.db = self.client[self.collection_name]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("MongoDB initialized successfully.")
            
            # Create indexes if they don't exist
            # Videos collection
            self.db.videos.create_index("terabox_id", unique=True)
            # Users collection
            self.db.users.create_index("user_id", unique=True)
            
        except Exception as e:
            logger.error(f"MongoDB initialization failed: {e}")

    def add_user(self, user_id, first_name, username):
        """Add a new user to the database."""
        try:
            user_data = {
                "user_id": user_id,
                "first_name": first_name,
                "username": username,
                "joined_at": int(time.time())
            }
            # Use update_one with upsert=True to mimic INSERT OR IGNORE / REPLACE
            # If user exists, we might not want to overwrite joined_at, so let's use $setOnInsert
            self.db.users.update_one(
                {"user_id": user_id},
                {"$setOnInsert": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user to DB: {e}")
            return False

    def get_all_users(self):
        """Get all user IDs."""
        try:
            users = self.db.users.find({}, {"user_id": 1})
            return [user["user_id"] for user in users]
        except Exception as e:
            logger.error(f"Error fetching users from DB: {e}")
            return []

    def get_video(self, terabox_id):
        """Retrieve video file_id by terabox_id."""
        try:
            video = self.db.videos.find_one({"terabox_id": terabox_id})
            if video:
                return (video["file_id"], video.get("title"))
            return None
        except Exception as e:
            logger.error(f"Error fetching video from DB: {e}")
            return None

    def add_video(self, terabox_id, file_id, title):
        """Add a new video mapping to the database."""
        try:
            video_data = {
                "terabox_id": terabox_id,
                "file_id": file_id,
                "title": title,
                "timestamp": int(time.time())
            }
            self.db.videos.update_one(
                {"terabox_id": terabox_id},
                {"$set": video_data},
                upsert=True
            )
            logger.info(f"Added video to DB: {terabox_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding video to DB: {e}")
            return False

    def delete_video(self, terabox_id):
        """Delete a video mapping from the database."""
        try:
            result = self.db.videos.delete_one({"terabox_id": terabox_id})
            logger.info(f"Deleted video from DB: {terabox_id} (Count: {result.deleted_count})")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting video from DB: {e}")
            return False
