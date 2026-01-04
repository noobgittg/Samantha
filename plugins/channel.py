import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from info import CHANNELS, ADMINS
from database.ia_filterdb import save_file

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return

    media.file_type = file_type
    media.caption = message.caption
    await save_file(media)

@Client.on_message(filters.command("channel") & filters.user(ADMINS))
async def channel_info(bot: Client, message: Message):
    try:
        if isinstance(CHANNELS, (int, str)):
            channels = [CHANNELS]
        elif isinstance(CHANNELS, list):
            channels = CHANNELS
        else:
            raise ValueError("Unexpected type for CHANNELS configuration.")

        text = "📜 **Indexed Channels / Groups:**\n"
        total = len(channels)

        for channel in channels:
            try:
                chat = await bot.get_chat(channel)
                if chat.username:
                    text += f"\n✅ @{chat.username}"
                else:
                    name = chat.title or chat.first_name or "Unnamed"
                    text += f"\n✅ {name}"
            except Exception as e:
                text += f"\n⚠️ Failed to fetch `{channel}` — ({e})"

        text += f"\n\n📊 **Total Indexed:** {total}"

        if len(text) < 4096:
            await message.reply_text(text)
        else:
            file_path = "Indexed_Channels.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            await message.reply_document(file_path)
            os.remove(file_path)

        print("📦 Channel info command executed successfully.")

    except Exception as e:
        error_text = f"🚨 **Error fetching channel info:**\n`{e}`"
        await message.reply_text(error_text)
        print(error_text)
