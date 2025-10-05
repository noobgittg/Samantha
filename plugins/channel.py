import re
import logging
from pyrogram import Client, filters
from info import CHANNELS, DELETE_CHANNELS
from database.ia_filterdb import Media, Media2, save_file

logger = logging.getLogger(__name__)

# Filters for media types
media_filter = filters.document | filters.video | filters.audio

# Databases list
DBS = [Media, Media2]


def extract_media(message):
    """Extracts the media object (document/video/audio) from a Pyrogram message."""
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media:
            return file_type, media
    return None, None


async def delete_from_dbs(query: dict) -> bool:
    """Delete a single record from any of the databases."""
    for db in DBS:
        result = await db.collection.delete_one(query)
        if result.deleted_count > 0:
            return True
    return False


async def delete_many_from_dbs(query: dict) -> bool:
    """Delete multiple records from any of the databases."""
    for db in DBS:
        result = await db.collection.delete_many(query)
        if result.deleted_count > 0:
            return True
    return False


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def save_media(bot: Client, message):
    """Handles media messages in CHANNELS and saves them to the database."""
    file_type, media = extract_media(message)
    if not media:
        return

    file_data = {
        "file_id": media.file_id,
        "file_unique_id": media.file_unique_id,
        "file_name": getattr(media, "file_name", None),
        "file_size": getattr(media, "file_size", None),
        "mime_type": getattr(media, "mime_type", None),
        "file_type": file_type,
        "caption": getattr(message, "caption", None),
    }

    try:
        await save_file(file_data)
        logger.info(f"✅ Saved file: {file_data['file_name']} ({file_data['file_unique_id']})")
    except Exception as e:
        logger.error(f"❌ Error saving file: {e}")


@Client.on_message(filters.chat(DELETE_CHANNELS) & media_filter)
async def delete_media(bot: Client, message):
    """Handles media messages in DELETE_CHANNELS and deletes them from the database."""
    file_type, media = extract_media(message)
    if not media:
        return

    # Try deleting by file_unique_id first
    if await delete_from_dbs({"file_unique_id": media.file_unique_id}):
        logger.info("✅ File successfully deleted from database (by unique_id).")
        return

    # Normalize filename for fallback
    file_name = str(getattr(media, "file_name", "") or "")
    file_name_norm = re.sub(r"[_\-\.\+]", " ", file_name).strip()

    query = {
        "file_name": file_name_norm,
        "file_size": getattr(media, "file_size", None),
        "mime_type": getattr(media, "mime_type", None),
    }

    # Try deleting by normalized name
    if await delete_many_from_dbs(query):
        logger.info("✅ File successfully deleted from database (by normalized name).")
        return

    # Final fallback: exact filename
    query["file_name"] = file_name
    if await delete_many_from_dbs(query):
        logger.info("✅ File successfully deleted from database (by exact name).")
    else:
        logger.warning("⚠️ File not found in database.")
