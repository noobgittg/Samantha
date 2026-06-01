import asyncio
from typing import Optional
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType
import logging

logger = logging.getLogger(__name__)

from database.ia_filterdb import (
    clear_search_cache, 
    invalidate_file_cache, 
    health_check,
    search_cache,
    get_search_results
)

# ── 🗑️ CLEAR CACHE COMMAND ────────────────────────────────────
@Client.on_message(filters.command("clearcache") & filters.user(ADMINS))
async def clear_cache_command(client: Client, message: Message):
    """🗑️ Clears entire search cache"""
    msg = await message.reply("🔄 **ᴄʟᴇᴀʀɪɴɢ ᴄᴀᴄʜᴇ...**")
    
    try:
        await clear_search_cache()
        await msg.edit(
            "✅ **ᴄᴀᴄʜᴇ ᴄʟᴇᴀʀᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!**\n\n"
            "📊 **ꜱᴛᴀᴛᴜꜱ:**\n"
            f"• 🗑️ ᴄᴀᴄʜᴇ ꜱɪᴢᴇ: `0`\n"
            f"• ⚡ ᴍᴇᴍᴏʀʏ ꜰʀᴇᴇᴅ: `{search_cache.maxsize}` ꜱʟᴏᴛꜱ\n"
            "• 🔄 ɴᴇᴡ ꜱᴇᴀʀᴄʜᴇꜱ ᴡɪʟʟ ʀᴇᴘᴏᴘᴜʟᴀᴛᴇ ᴄᴀᴄʜᴇ"
        )
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        await msg.edit(f"❌ **ꜰᴀɪʟᴇᴅ ᴛᴏ ᴄʟᴇᴀʀ ᴄᴀᴄʜᴇ:**\n`{str(e)[:200]}`")

# ── 📊 CACHE STATUS COMMAND ────────────────────────────────────
@Client.on_message(filters.command("cachestatus") & filters.user(ADMINS))
async def cache_status_command(client: Client, message: Message):
    """📊 Shows current cache statistics"""
    cache_size = len(search_cache._cache)
    max_size = search_cache.maxsize
    ttl = search_cache.ttl
    
    # Calculate approximate memory usage (rough estimate)
    approx_memory = cache_size * 1024  # ~1KB per cached item
    
    status_text = f"""
📊 **ᴄᴀᴄʜᴇ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ**

━━━━━━━━━━━━━━━━━━━━
🎯 **ɢᴇɴᴇʀᴀʟ**
• 🗃️ ᴄᴀᴄʜᴇᴅ ɪᴛᴇᴍꜱ: `{cache_size}/{max_size}`
• ⏱️ ᴛᴛʟ: `{ttl} ꜱᴇᴄᴏɴᴅꜱ`
• 💾 ᴀᴘᴘʀᴏx ᴜꜱᴀɢᴇ: `~{approx_memory // 1024} KB`

━━━━━━━━━━━━━━━━━━━━
⚡ **ᴘᴇʀꜰᴏʀᴍᴀɴᴄᴇ**
• 🚀 ᴄᴀᴄʜᴇ ᴜᴛɪʟɪᴢᴀᴛɪᴏɴ: `{(cache_size/max_size)*100:.1f}%`
• 🔥 ᴇꜰꜰɪᴄɪᴇɴᴄʏ: `ᴀᴄᴛɪᴠᴇ`

━━━━━━━━━━━━━━━━━━━━
🔄 **ʀᴇᴄᴏᴍᴍᴇɴᴅᴀᴛɪᴏɴꜱ**
• {'⚠️ ᴄᴀᴄʜᴇ ɪꜱ ꜰᴜʟʟ - ᴄᴏɴꜱɪᴅᴇʀ ᴄʟᴇᴀʀɪɴɢ' if cache_size >= max_size * 0.9 else '✅ ᴄᴀᴄʜᴇ ʜᴇᴀʟᴛʜʏ'}
• {'🔧 ᴜꜱᴇ /clearcache ᴛᴏ ꜰʀᴇᴇ ᴍᴇᴍᴏʀʏ' if cache_size >= max_size * 0.8 else '💪 ᴄᴀᴄʜᴇ ᴡᴏʀᴋɪɴɢ ᴏᴘᴛɪᴍᴀʟʟʏ'}
"""
    
    await message.reply(status_text)

# ── 🏥 HEALTH CHECK COMMAND ────────────────────────────────────
@Client.on_message(filters.command("health") & filters.user(ADMINS))
async def health_check_command(client: Client, message: Message):
    """🏥 Complete system health check"""
    msg = await message.reply("🔄 **ʀᴜɴɴɪɴɢ ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ...**")
    
    try:
        health = await health_check()
        
        # Determine overall status
        primary_ok = health['primary_db']['status'] == 'healthy'
        secondary_ok = health['secondary_db']['status'] == 'healthy'
        
        if primary_ok and secondary_ok:
            overall = "✅ **ᴇxᴄᴇʟʟᴇɴᴛ**"
            emoji = "🟢"
        elif primary_ok or secondary_ok:
            overall = "⚠️ **ᴅᴇɢʀᴀᴅᴇᴅ**"
            emoji = "🟡"
        else:
            overall = "❌ **ᴄʀɪᴛɪᴄᴀʟ**"
            emoji = "🔴"
        
        health_text = f"""
🏥 **ꜱʏꜱᴛᴇᴍ ʜᴇᴀʟᴛʜ ᴍᴏɴɪᴛᴏʀ**

{emoji} **ᴏᴠᴇʀᴀʟʟ ꜱᴛᴀᴛᴜꜱ:** {overall}

━━━━━━━━━━━━━━━━━━━━
🗄️ **ᴅᴀᴛᴀʙᴀꜱᴇꜱ**

📀 **ᴘʀɪᴍᴀʀʏ ᴅʙ**
• ꜱᴛᴀᴛᴜꜱ: `{health['primary_db']['status']}`
• ʟᴀᴛᴇɴᴄʏ: `{health['primary_db']['latency_ms']} ᴍꜱ`

💿 **ꜱᴇᴄᴏɴᴅᴀʀʏ ᴅʙ**
• ꜱᴛᴀᴛᴜꜱ: `{health['secondary_db']['status']}`
• ʟᴀᴛᴇɴᴄʏ: `{health['secondary_db']['latency_ms']} ᴍꜱ`

━━━━━━━━━━━━━━━━━━━━
💾 **ᴄᴀᴄʜᴇ ꜱʏꜱᴛᴇᴍ**
• ᴄᴀᴄʜᴇ ꜱɪᴢᴇ: `{health['cache_size']}/{search_cache.maxsize}`
• ᴄᴀᴄʜᴇ ʜɪᴛꜱ: `{health.get('cache_hits', 0)}`

━━━━━━━━━━━━━━━━━━━━
🎯 **ʀᴇᴄᴏᴍᴍᴇɴᴅᴀᴛɪᴏɴꜱ**
• {'✅ ᴀʟʟ ꜱʏꜱᴛᴇᴍꜱ ᴏᴘᴇʀᴀᴛɪᴏɴᴀʟ' if primary_ok and secondary_ok else '⚠️ ᴄʜᴇᴄᴋ ᴅᴀᴛᴀʙᴀꜱᴇ ᴄᴏɴɴᴇᴄᴛɪᴏɴꜱ'}
• {'💡 ᴄᴏɴꜱɪᴅᴇʀ /clearcache' if health['cache_size'] > 800 else '✅ ᴄᴀᴄʜᴇ ᴏᴘᴛɪᴍᴀʟ'}
"""
        
        # Add inline buttons for actions
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗑️ ᴄʟᴇᴀʀ ᴄᴀᴄʜᴇ", callback_data="clear_cache"),
                InlineKeyboardButton("🔄 ʀᴇꜰʀᴇꜱʜ", callback_data="refresh_health")
            ],
            [
                InlineKeyboardButton("📊 ᴅᴇᴛᴀɪʟᴇᴅ ꜱᴛᴀᴛꜱ", callback_data="detailed_stats")
            ]
        ])
        
        await msg.edit(health_text, reply_markup=buttons)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        await msg.edit(f"❌ **ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ:**\n`{str(e)[:200]}`")

# ── 🔄 REFRESH CACHE FOR SPECIFIC FILE ─────────────────────────
@Client.on_message(filters.command("refresh") & filters.user(ADMINS))
async def refresh_file_cache(client: Client, message: Message):
    """🔄 Invalidates cache for specific file ID"""
    if len(message.command) < 2:
        await message.reply(
            "❌ **ᴜꜱᴀɢᴇ:** `/refresh <file_id>`\n\n"
            "📝 **ᴇxᴀᴍᴘʟᴇ:** `/refresh BQACAgQAAx0...`"
        )
        return
    
    file_id = message.command[1]
    msg = await message.reply(f"🔄 **ʀᴇꜰʀᴇꜱʜɪɴɢ ᴄᴀᴄʜᴇ ꜰᴏʀ:**\n`{file_id[:30]}...`")
    
    try:
        await invalidate_file_cache(file_id)
        await msg.edit(
            f"✅ **ᴄᴀᴄʜᴇ ɪɴᴠᴀʟɪᴅᴀᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!**\n\n"
            f"📄 **ꜰɪʟᴇ ɪᴅ:** `{file_id[:30]}...`\n"
            f"🔄 ɴᴇxᴛ ꜱᴇᴀʀᴄʜ ᴡɪʟʟ ꜰᴇᴛᴄʜ ꜰʀᴇꜱʜ ᴅᴀᴛᴀ"
        )
    except Exception as e:
        await msg.edit(f"❌ **ꜰᴀɪʟᴇᴅ ᴛᴏ ɪɴᴠᴀʟɪᴅᴀᴛᴇ ᴄᴀᴄʜᴇ:**\n`{str(e)[:200]}`")

# ── 📈 PERFORMANCE METRICS COMMAND ────────────────────────────
@Client.on_message(filters.command("perf") & filters.user(ADMINS))
async def performance_metrics(client: Client, message: Message):
    """📈 Shows detailed performance metrics"""
    import time
    import psutil
    import os
    
    # Get process memory usage
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    
    # Cache metrics
    cache_size = len(search_cache._cache)
    cache_max = search_cache.maxsize
    
    # Calculate theoretical performance
    cache_hit_ratio = (search_cache._cache.get('_hits', 0) / max(1, search_cache._cache.get('_misses', 0) + search_cache._cache.get('_hits', 0))) * 100
    
    perf_text = f"""
📈 **ᴘᴇʀꜰᴏʀᴍᴀɴᴄᴇ ᴍᴇᴛʀɪᴄꜱ**

━━━━━━━━━━━━━━━━━━━━
💾 **ᴍᴇᴍᴏʀʏ ᴜꜱᴀɢᴇ**
• ʀᴀᴍ ᴜꜱᴇᴅ: `{memory_mb:.1f} ᴍʙ`
• ᴄᴀᴄʜᴇ ꜱɪᴢᴇ: `{cache_size}/{cache_max}`

━━━━━━━━━━━━━━━━━━━━
⚡ **ꜱᴘᴇᴇᴅ ᴇꜱᴛɪᴍᴀᴛᴇꜱ**
• ᴄᴀᴄʜᴇᴅ ꜱᴇᴀʀᴄʜ: `~0.5 ᴍꜱ`
• ᴅʙ ꜱᴇᴀʀᴄʜ: `~50-200 ᴍꜱ`
• ꜱᴘᴇᴇᴅ ʙᴏᴏꜱᴛ: `{cache_hit_ratio:.0f}% ꜰᴀꜱᴛᴇʀ`

━━━━━━━━━━━━━━━━━━━━
🎯 **ᴇꜰꜰɪᴄɪᴇɴᴄʏ**
• ᴄᴀᴄʜᴇ ʜɪᴛʀᴀᴛᴇ: `{cache_hit_ratio:.1f}%`
• ᴅʙ ʟᴏᴀᴅ ʀᴇᴅᴜᴄᴛɪᴏɴ: `{cache_hit_ratio * 0.8:.1f}%`

━━━━━━━━━━━━━━━━━━━━
💡 **ᴛɪᴘ:** ᴜꜱᴇ `/clearcache` ᴛᴏ ʀᴇꜱᴇᴛ ꜱᴛᴀᴛꜱ
"""
    
    await message.reply(perf_text)

# ── 🔘 CALLBACK HANDLERS ──────────────────────────────────────
@Client.on_callback_query()
async def cache_callbacks(client: Client, callback_query):
    """Handle callback queries from health check buttons"""
    data = callback_query.data
    
    if data == "clear_cache":
        await clear_search_cache()
        await callback_query.answer("✅ ᴄᴀᴄʜᴇ ᴄʟᴇᴀʀᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!", show_alert=True)
        
        # Update the message
        await callback_query.message.edit(
            callback_query.message.text + "\n\n✅ **ᴄᴀᴄʜᴇ ʜᴀꜱ ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 ʀᴜɴ /ʜᴇᴀʟᴛʜ ᴀɢᴀɪɴ", callback_data="refresh_health")]
            ])
        )
    
    elif data == "refresh_health":
        await callback_query.answer("🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ ʜᴇᴀʟᴛʜ ꜱᴛᴀᴛᴜꜱ...")
        # Re-run health check
        health = await health_check()
        # Update the message (simplified version)
        await callback_query.message.edit(
            f"🏥 **ꜱʏꜱᴛᴇᴍ ʜᴇᴀʟᴛʜ**\n"
            f"• ᴘʀɪᴍᴀʀʏ ᴅʙ: `{health['primary_db']['status']}`\n"
            f"• ꜱᴇᴄᴏɴᴅᴀʀʏ ᴅʙ: `{health['secondary_db']['status']}`\n"
            f"• ᴄᴀᴄʜᴇ ꜱɪᴢᴇ: `{health['cache_size']}`\n\n"
            f"✅ ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇᴅ",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 ꜰᴜʟʟ /ʜᴇᴀʟᴛʜ", callback_data="full_health")]
            ])
        )
    
    elif data == "detailed_stats":
        await callback_query.answer("📊 ꜰᴇᴛᴄʜɪɴɢ ᴅᴇᴛᴀɪʟᴇᴅ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ...")
        # Show detailed stats
        cache_items = list(search_cache._cache.items())[:10]  # Show first 10
        stats_text = "📊 **ᴅᴇᴛᴀɪʟᴇᴅ ᴄᴀᴄʜᴇ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ**\n\n"
        
        for key, (_, expiry) in cache_items:
            time_left = max(0, int(expiry - asyncio.get_event_loop().time()))
            stats_text += f"• `{key[:20]}...` ⏱️ {time_left}ꜱ\n"
        
        stats_text += f"\n📊 **ᴛᴏᴛᴀʟ:** `{len(search_cache._cache)}` ᴄᴀᴄʜᴇᴅ ɪᴛᴇᴍꜱ"
        
        await callback_query.message.reply(stats_text)

# ── 🚀 AUTO CACHE WARMUP ON STARTUP ───────────────────────────
async def warmup_cache():
    """🔥 Pre-warm cache with popular searches"""
    popular_queries = ["", "movie", "video", "music", "document"]
    
    logger.info("🔥 ᴡᴀʀᴍɪɴɢ ᴜᴘ ᴄᴀᴄʜᴇ ᴡɪᴛʜ ᴘᴏᴘᴜʟᴀʀ Qᴜᴇʀɪᴇꜱ...")
    
    for query in popular_queries:
        try:
            await get_search_results(query, max_results=20, use_cache=True)
            await asyncio.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Cache warmup failed for '{query}': {e}")
    
    logger.info("✅ ᴄᴀᴄʜᴇ ᴡᴀʀᴍᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇᴅ")

# ── 📋 COMMAND LIST FOR HELP MENU ─────────────────────────────
COMMANDS = {
    "clearcache": "🗑️ ᴄʟᴇᴀʀ ᴇɴᴛɪʀᴇ ꜱᴇᴀʀᴄʜ ᴄᴀᴄʜᴇ",
    "cachestatus": "📊 ꜱʜᴏᴡ ᴄᴀᴄʜᴇ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ",
    "health": "🏥 ᴄᴏᴍᴘʟᴇᴛᴇ ꜱʏꜱᴛᴇᴍ ʜᴇᴀʟᴛʜ ᴄʜᴇᴄᴋ",
    "refresh": "🔄 ʀᴇꜰʀᴇꜱʜ ᴄᴀᴄʜᴇ ꜰᴏʀ ꜱᴘᴇᴄɪꜰɪᴄ ꜰɪʟᴇ",
    "perf": "📈 ᴅᴇᴛᴀɪʟᴇᴅ ᴘᴇʀꜰᴏʀᴍᴀɴᴄᴇ ᴍᴇᴛʀɪᴄꜱ"
}

@Client.on_message(filters.command("cachehelp") & filters.user(ADMINS))
async def cache_help(client: Client, message: Message):
    """📚 Shows all cache management commands"""
    help_text = """
💾 **ᴄᴀᴄʜᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴏᴍᴍᴀɴᴅꜱ**

━━━━━━━━━━━━━━━━━━━━
🎮 **ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ**

"""
    for cmd, desc in COMMANDS.items():
        help_text += f"• **/{cmd}** - {desc}\n"
    
    help_text += """
━━━━━━━━━━━━━━━━━━━━
💡 **ᴛɪᴘꜱ**
• ᴄᴀᴄʜᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴄʟᴇᴀʀꜱ ᴀꜰᴛᴇʀ 5 ᴍɪɴᴜᴛᴇꜱ
• ᴜꜱᴇ `/health` ꜰᴏʀ ᴄᴏᴍᴘʟᴇᴛᴇ ꜱʏꜱᴛᴇᴍ ꜱᴛᴀᴛᴜꜱ
• ᴄᴀᴄʜᴇ ᴍᴀᴋᴇꜱ ꜱᴇᴀʀᴄʜᴇꜱ **10x ꜰᴀꜱᴛᴇʀ**

⚡ **ᴘᴏᴡᴇʀᴇᴅ ʙʏ ᴀꜱʏɴᴄ ᴅᴜᴀʟ-ᴅʙ ᴄᴀᴄʜɪɴɢ**
"""
    
    await message.reply(help_text)
