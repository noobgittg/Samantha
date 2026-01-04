import logging
from pyrogram import Client, emoji, filters
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument, InlineQuery
from database.ia_filterdb import get_search_results
from utils import is_subscribed, get_size, temp
from info import *

logger = logging.getLogger(__name__)
cache_time = 0 if AUTH_USERS or AUTH_CHANNEL else CACHE_TIME

async def inline_users(query: InlineQuery):
    logger.info(f"🔍 Inline query check for user {query.from_user.id if query.from_user else 'unknown'}")
    if AUTH_USERS:
        if query.from_user and query.from_user.id in AUTH_USERS:
            logger.info("✅ User authorized via AUTH_USERS")
            return True
        else:
            logger.warning("❌ User not in AUTH_USERS")
            return False
    if query.from_user and query.from_user.id not in temp.BANNED_USERS:
        logger.info("✅ User not banned")
        return True
    logger.warning("🚫 User banned or invalid")
    return False

@Client.on_inline_query()
async def answer(bot, query):
    logger.info(f"🌐 Handling inline query: {query.query} from user {query.from_user.id if query.from_user else 'unknown'}")
    if not await inline_users(query):
        logger.warning("🚫 Unauthorized inline query - empty response")
        await query.answer(results=[],
                           cache_time=0,
                           switch_pm_text='okDa',
                           switch_pm_parameter="hehe")
        return

    logger.info("📋 Checking subscription status...")
    invite_links = await is_subscribed(bot, query=query)
    if AUTH_CHANNEL and len(invite_links) >= 1:
        logger.warning("⚠️ Force subscribe required - empty response")
        await query.answer(results=[],
            cache_time=0,
            switch_pm_text='You have to subscribe my channel to use the bot',
            switch_pm_parameter="subscribe")
        return

    results = []
    logger.info(f"🔍 Parsing query: '{query.query}'")
    if '|' in query.query:
        string, file_type = query.query.split('|', maxsplit=1)
        string = string.strip()
        file_type = file_type.strip().lower()
        logger.info(f"📂 Parsed: string='{string}', file_type='{file_type}'")
    else:
        string = query.query.strip()
        file_type = None
        logger.info(f"📂 Parsed: string='{string}', file_type=None")

    offset = int(query.offset or 0)
    logger.info(f"📄 Offset: {offset}")
    reply_markup = get_reply_markup(query=string)
    logger.info("🔗 Generated reply markup")

    logger.info(f"🗄️ Fetching search results for '{string}' (type: {file_type}, offset: {offset}, max: 10)")
    files, next_offset, total = await get_search_results(string,
                                                  file_type=file_type,
                                                  max_results=10,
                                                  offset=offset)
    logger.info(f"📊 Search results: {len(files)} files, next_offset: {next_offset}, total: {total}")

    for file in files:
        logger.info(f"📁 Processing file: {file.file_name} (size: {file.file_size})")
        title = file.file_name
        size = get_size(file.file_size)
        f_caption = file.caption
        if CUSTOM_FILE_CAPTION:
            try:
                f_caption = CUSTOM_FILE_CAPTION.format(file_name='' if title is None else title,
                                                      file_size='' if size is None else size,
                                                      file_caption='' if f_caption is None else f_caption)
                logger.info("✏️ Custom caption applied successfully")
            except Exception as e:
                logger.exception(f"❌ Custom caption error: {e}")
                f_caption = f_caption
        if f_caption is None:
            f_caption = f"{file.file_name}"
        results.append(
            InlineQueryResultCachedDocument(
                title=file.file_name,
                document_file_id=file.file_id,
                caption=f_caption,
                description=f'Size: {get_size(file.file_size)}\nType: {file.file_type}',
                reply_markup=reply_markup))
        logger.info(f"✅ Added result for {file.file_name}")

    if results:
        switch_pm_text = f"{emoji.FILE_FOLDER} Results - {total}"
        if string:
            switch_pm_text += f" for {string}"
        logger.info(f"📤 Answering with {len(results)} results | Switch PM: {switch_pm_text}")
        try:
            await query.answer(results=results,
                               is_personal=True,
                               cache_time=cache_time,
                               switch_pm_text=switch_pm_text,
                               switch_pm_parameter="start",
                               next_offset=str(next_offset))
            logger.info("✅ Inline query answered successfully")
        except QueryIdInvalid:
            logger.warning("⚠️ Query ID invalid - skipping answer")
            pass
        except Exception as e:
            logger.exception(f"❌ Error in query.answer: {e}")
            # Fallback: Answer with error info if needed, but keep empty for now
            await query.answer(results=[], cache_time=0, switch_pm_text=f'❌ Error: {str(e)[:50]}...', switch_pm_parameter="error")
    else:
        switch_pm_text = f'{emoji.CROSS_MARK} No results'
        if string:
            switch_pm_text += f' for "{string}"'
        logger.info(f"📭 No results - answering empty with: {switch_pm_text}")
        await query.answer(results=[],
                           is_personal=True,
                           cache_time=cache_time,
                           switch_pm_text=switch_pm_text,
                           switch_pm_parameter="okay")


def get_reply_markup(query):
    buttons = [
        [
            InlineKeyboardButton('Search again', switch_inline_query_current_chat=query)
        ]
        ]
    return InlineKeyboardMarkup(buttons)
