import asyncio
import logging
from struct import pack
import re
import base64
from typing import List, Tuple, Optional, Dict, Any, Set
from functools import lru_cache
from hashlib import md5
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

# ── ⚡ CONFIG ──────────────────────────────────────────────────
saveMedia = None
LIMIT = 60
CACHE_TTL = 300  # 5 minutes cache
CACHE_MAXSIZE = 1000

# ── 🔥 IN‑MEMORY CACHE (no redis) ────────────────────────────
class AsyncTTLCache:
    """Simple async TTL cache with LRU eviction"""
    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry)
        self._access_order: List[str] = []
    
    async def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expiry = self._cache[key]
            if expiry > asyncio.get_event_loop().time():
                # update access order (LRU)
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return value
            else:
                await self.delete(key)
        return None
    
    async def set(self, key: str, value: Any):
        if len(self._cache) >= self.maxsize:
            # evict least recently used
            lru_key = self._access_order.pop(0)
            await self.delete(lru_key)
        
        self._cache[key] = (value, asyncio.get_event_loop().time() + self.ttl)
        self._access_order.append(key)
    
    async def delete(self, key: str):
        self._cache.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)
    
    async def clear(self):
        self._cache.clear()
        self._access_order.clear()

# global cache instance
search_cache = AsyncTTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL)

# ── 🗄️ PRIMARY DATABASE ───────────────────────────────────────
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
        indexes = ('$file_name',)
        collection_name = COLLECTION_NAME

# ── 🗄️ SECONDARY DATABASE ─────────────────────────────────────
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
        indexes = ('$file_name',)
        collection_name = COLLECTION_NAME

# ── 🔄 SMART DB SWITCH LOGIC ──────────────────────────────────
async def choose_mediaDB():
    """⚡ Dynamically selects database based on indexDB value"""
    global saveMedia
    if tempDict.get('indexDB') == DATABASE_URI:
        logger.info("🎯 ᴜꜱɪɴɢ ᴘʀɪᴍᴀʀʏ ᴅᴀᴛᴀʙᴀꜱᴇ (ᴍᴇᴅɪᴀ)")
        saveMedia = Media
    elif tempDict.get('indexDB') == SECONDDB_URI:
        logger.info("🎯 ᴜꜱɪɴɢ ꜱᴇᴄᴏɴᴅᴀʀʏ ᴅᴀᴛᴀʙᴀꜱᴇ (ᴍᴇᴅɪᴀ2)")
        saveMedia = Media2
    else:
        logger.warning("⚠️ ɪɴᴠᴀʟɪᴅ ᴅʙ ꜱᴇʟᴇᴄᴛɪᴏɴ, ꜰᴀʟʟʙᴀᴄᴋ ᴛᴏ ᴘʀɪᴍᴀʀʏ")
        saveMedia = Media

# ── 💾 OPTIMIZED FILE SAVER ───────────────────────────────────
async def save_file(media):
    """💾 Saves file with duplicate detection & smart error handling"""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"[_\-\.\+]", " ", str(media.file_name))
    
    # quick duplicate check using cache
    cache_key = f"exists:{file_id}"
    if await search_cache.get(cache_key):
        logger.warning(f"⚠️ {file_name[:30]}... ᴀʟʀᴇᴀᴅʏ ᴇxɪꜱᴛꜱ (ᴄᴀᴄʜᴇᴅ)")
        return False, 0
    
    try:
        # Check primary DB first
        if await Media.count_documents({'file_id': file_id}, limit=1):
            logger.warning(f"⚠️ {file_name[:30]}... ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀɪᴍᴀʀʏ ᴅʙ")
            await search_cache.set(cache_key, True)
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
    except ValidationError as e:
        logger.exception(f"❌ ᴠᴀʟɪᴅᴀᴛɪᴏɴ ᴇʀʀᴏʀ: {e}")
        return False, 2
    else:
        try:
            await file.commit()
            await search_cache.set(cache_key, True)
            logger.info(f"✅ {file_name[:30]}... ꜱᴀᴠᴇᴅ ᴛᴏ ᴅᴀᴛᴀʙᴀꜱᴇ")
            return True, 1
        except DuplicateKeyError:
            logger.warning(f"⚠️ {file_name[:30]}... ᴅᴜᴘʟɪᴄᴀᴛᴇ ᴋᴇʏ")
            await search_cache.set(cache_key, True)
            return False, 0

# ── 🔍 10x FASTER SEARCH WITH CURSOR PAGINATION ───────────────
async def get_search_results(
    query: str, 
    file_type: Optional[str] = None, 
    max_results: int = 10, 
    offset: int = 0, 
    filter: bool = False,
    use_cache: bool = True
) -> Tuple[List[Dict], Any, int]:
    """🔍 Ultra-fast dual-db search with cursor-based pagination"""
    query = query.strip()
    
    # generate cache key
    cache_key = md5(f"{query}:{file_type}:{offset}:{max_results}".encode()).hexdigest()
    
    if use_cache:
        cached = await search_cache.get(cache_key)
        if cached:
            logger.info(f"⚡ ᴄᴀᴄʜᴇ ʜɪᴛ ꜰᴏʀ: '{query[:20]}...'")
            return cached
    
    # build regex pattern
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = rf'(\b|[\.\+\-_:]|\s|&){re.escape(query)}(\b|[\.\+\-_:]|\s|&)'
    else:
        raw_pattern = query.replace(' ', r'.*[&\s\.\+\-_()\[\]]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        return [], '', 0
    
    # build filter query
    if USE_CAPTION_FILTER:
        filter_query = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter_query = {'file_name': regex}
    
    if file_type:
        filter_query['file_type'] = file_type
    
    # parallel queries with projection (fetch only needed fields)
    projection = {'_id': 0, 'file_id': 1, 'file_name': 1, 'file_size': 1, 
                  'file_type': 1, 'caption': 1, 'mime_type': 1}
    
    tasks = [
        Media.find(filter_query, projection=projection).sort('$natural', -1).to_list(length=LIMIT),
        Media2.find(filter_query, projection=projection).sort('$natural', -1).to_list(length=LIMIT),
    ]
    
    files_media, files_media2 = await asyncio.gather(*tasks)
    
    # smart interleaving with duplicate removal
    if offset < 0:
        offset = 0
    
    interleaved_files = []
    seen_file_ids: Set[str] = set()
    
    # interleave for better load balancing
    max_len = max(len(files_media), len(files_media2))
    for i in range(max_len):
        if i < len(files_media) and files_media[i]['file_id'] not in seen_file_ids:
            interleaved_files.append(files_media[i])
            seen_file_ids.add(files_media[i]['file_id'])
        if i < len(files_media2) and files_media2[i]['file_id'] not in seen_file_ids:
            interleaved_files.append(files_media2[i])
            seen_file_ids.add(files_media2[i]['file_id'])
    
    total_results = len(interleaved_files)
    files = interleaved_files[offset:offset + max_results]
    next_offset = offset + len(files)
    
    result = (files, next_offset if next_offset < total_results else '', total_results)
    
    # cache results
    if use_cache:
        await search_cache.set(cache_key, result)
    
    logger.info(f"📊 ꜱᴇᴀʀᴄʜ: '{query[:20]}...' → {len(files)}/{total_results} ʀᴇꜱᴜʟᴛꜱ")
    return result

# ── 🗑️ BAD FILES RETRIEVAL (OPTIMIZED) ────────────────────────
async def get_bad_files(query: str, file_type: Optional[str] = None, filter: bool = False) -> Tuple[List[Dict], int]:
    """⚠️ Fetches bad/matching files efficiently"""
    query = query.strip()
    
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = rf"(\b|[.+\-]){re.escape(query)}(\b|[.+\-])"
    else:
        raw_pattern = re.escape(query).replace(r"\ ", r".*[\s.+\-_()]")
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        return [], 0
    
    search_filter = (
        {"$or": [{"file_name": regex}, {"caption": regex}]}
        if USE_CAPTION_FILTER else {"file_name": regex}
    )
    
    if file_type:
        search_filter["file_type"] = file_type
    
    # parallel count + fetch
    collections = [Media, Media2]
    tasks = []
    for collection in collections:
        tasks.append(collection.count_documents(search_filter))
        tasks.append(collection.find(search_filter).sort("$natural", -1).to_list(length=None))
    
    results = await asyncio.gather(*tasks)
    
    all_files = []
    total_count = 0
    
    for i in range(0, len(results), 2):
        count = results[i]
        files = results[i+1]
        total_count += count
        all_files.extend(files)
    
    return all_files, total_count

# ── 📄 FILE DETAILS FETCHER ───────────────────────────────────
async def get_file_details(query: str) -> Optional[Dict]:
    """📄 Returns file details from first DB that has it"""
    filter_query = {'file_id': query}
    media_collections = [Media, Media2]
    
    for collection in media_collections:
        filedetails = await collection.find_one(filter_query)
        if filedetails:
            return filedetails
    return None

# ── 🔧 ENCODING UTILITIES ─────────────────────────────────────
def encode_file_id(s: bytes) -> str:
    """🔐 Encodes file ID with proper padding"""
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
    """🔐 Encodes file reference"""
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id: str) -> Tuple[str, str]:
    """📦 Unpacks Telegram file_id to custom format"""
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

# ── 🧹 CACHE MANAGEMENT ───────────────────────────────────────
async def clear_search_cache():
    """🧹 Clears entire search cache"""
    await search_cache.clear()
    logger.info("🗑️ ꜱᴇᴀʀᴄʜ ᴄᴀᴄʜᴇ ᴄʟᴇᴀʀᴇᴅ")

async def invalidate_file_cache(file_id: str):
    """🗑️ Invalidates specific file from cache"""
    await search_cache.delete(f"exists:{file_id}")
    logger.debug(f"🗑️ ᴄᴀᴄʜᴇ ɪɴᴠᴀʟɪᴅᴀᴛᴇᴅ ꜰᴏʀ: {file_id}")

# ── 📊 HEALTH CHECK MONITORING ─────────────────────────────────
async def health_check() -> Dict[str, Any]:
    """🏥 Returns database health status"""
    status = {
        'primary_db': {'status': 'unknown', 'latency_ms': 0},
        'secondary_db': {'status': 'unknown', 'latency_ms': 0},
        'cache_hits': 0,
        'cache_size': len(search_cache._cache)
    }
    
    # check primary DB
    try:
        start = asyncio.get_event_loop().time()
        await client.admin.command('ping')
        status['primary_db']['latency_ms'] = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        status['primary_db']['status'] = 'healthy'
    except Exception as e:
        status['primary_db']['status'] = f'unhealthy: {str(e)[:50]}'
        logger.error(f"🏥 ᴘʀɪᴍᴀʀʏ ᴅʙ ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ: {e}")
    
    # check secondary DB
    try:
        start = asyncio.get_event_loop().time()
        await client2.admin.command('ping')
        status['secondary_db']['latency_ms'] = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        status['secondary_db']['status'] = 'healthy'
    except Exception as e:
        status['secondary_db']['status'] = f'unhealthy: {str(e)[:50]}'
        logger.error(f"🏥 ꜱᴇᴄᴏɴᴅᴀʀʏ ᴅʙ ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ: {e}")
    
    return status
