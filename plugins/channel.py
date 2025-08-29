import re
import logging
from pyrogram import Client, filters
from info import DELETE_CHANNELS, CHANNELS
from database.ia_filterdb import Media, Media2, unpack_new_file_id, save_file

logger = logging.getLogger(__name__)

media_filter = filters.document | filters.video | filters.audio
DBS = [Media, Media2]


def extract_media(message):
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media:
            media.file_type = file_type
            media.caption = message.caption
            return media
    return None


async def delete_from_dbs(query):
    for db in DBS:
        result = await db.collection.delete_one(query)
        if result.deleted_count:
            return True
    return False


async def delete_many_from_dbs(query):
    for db in DBS:
        result = await db.collection.delete_many(query)
        if result.deleted_count:
            return True
    return False


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    media = extract_media(message)
    if media:
        await save_file(media)


@Client.on_message(filters.chat(DELETE_CHANNELS) & media_filter)
async def deletemultiplemedia(bot, message):
    media = extract_media(message)
    if not media:
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)

    if await delete_from_dbs({"_id": file_id}):
        logger.info("File successfully deleted from database.")
        return

    file_name_norm = re.sub(r"[_\-\.\+]", " ", str(media.file_name))
    query = {
        "file_name": file_name_norm,
        "file_size": media.file_size,
        "mime_type": media.mime_type,
    }
    if await delete_many_from_dbs(query):
        logger.info("File successfully deleted from database.")
        return

    query["file_name"] = media.file_name
    if await delete_many_from_dbs(query):
        logger.info("File successfully deleted from database.")
    else:
        logger.info("File not found in database.")
