import asyncio
import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import *
from utils import get_settings, save_group_settings
from sample_info import tempDict 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

#some basic variables needed
saveMedia = None
LIMIT = 60

#primary db
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

#secondary db
client2 = AsyncIOMotorClient(SECONDDB_URI)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)

@instance2.register
class Media2(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

async def choose_mediaDB():
    """This Function chooses which database to use based on the value of indexDB key in the dict tempDict."""
    global saveMedia
    if tempDict['indexDB'] == DATABASE_URI:
        logger.info("Using first db (Media)")
        saveMedia = Media
    else:
        logger.info("Using second db (Media2)")
        saveMedia = Media2

async def save_file(media):
    """Save file in database"""

    # TODO: Find better way to get same file_id for same media to avoid duplicates
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    try:
        if await Media.count_documents({'file_id': file_id}, limit=1):
            logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in primary DB !')
            return False, 0
        file = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception('Error occurred while saving file in database')
        return False, 2
    else:
        try:
            await file.commit()
        except DuplicateKeyError:  
            logger.warning(
                f'{getattr(media, "file_name", "NO_FILE")} is already saved in database'
            )

            return False, 0
        else:
            logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
            return True, 1

async def get_search_results(query, file_type=None, max_results=10, offset=0, filter=False):
    query = query.strip()

    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_:]|\s|&)' + query + r'(\b|[\.\+\-_:]|\s|&)'
    else:
        raw_pattern = query.replace(' ', r'.*[&\s\.\+\-_()\[\]:]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return [], '', 0

    if USE_CAPTION_FILTER:
        filter_query = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter_query = {'file_name': regex}

    if file_type:
        filter_query['file_type'] = file_type

    tasks = [
        Media.find(filter_query).sort('$natural', -1).to_list(length=LIMIT),
        Media2.find(filter_query).sort('$natural', -1).to_list(length=LIMIT),
    ]

    files_media, files_media2 = await asyncio.gather(*tasks)

    if offset < 0:
        offset = 0

    interleaved_files = []
    seen_file_ids = set()

    all_files = files_media + files_media2

    for file in all_files:
        if file['file_id'] not in seen_file_ids:
            interleaved_files.append(file)
            seen_file_ids.add(file['file_id'])

    files = interleaved_files[offset:offset + max_results]
    total_results = len(interleaved_files)
    next_offset = offset + len(files)

    if next_offset < total_results:
        return files, next_offset, total_results
    else:
        return files, '', total_results

async def get_bad_files(query, file_type=None, filter=False):
    query = query.strip()
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = rf"(\b|[.\+\-_]){re.escape(query)}(\b|[.\+\-_])"
    else:
        raw_pattern = re.escape(query).replace(r"\ ", r".*[\s.\+\-_()]")

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        return [], 0

    search_filter = (
        {"$or": [{"file_name": regex}, {"caption": regex}]}
        if USE_CAPTION_FILTER
        else {"file_name": regex}
    )

    if file_type:
        search_filter["file_type"] = file_type

    # Collections to search
    collections = [Media, Media2]
    files = []

    for collection in collections:
        cursor = collection.find(search_filter).sort("$natural", -1)
        count = await collection.count_documents(search_filter)
        if count > 0:
            files.extend(await cursor.to_list(length=count))

    return files, len(files)


async def get_file_details(query):
    filter_query = {'file_id': query}
    media_collections = [Media, Media2]

    for collection in media_collections:
        cursor = collection.find(filter_query)
        filedetails = await cursor.to_list(length=1)
        if filedetails:
            return filedetails

def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])

    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
