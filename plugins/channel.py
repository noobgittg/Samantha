import os
from pyrogram import Client, filters
from pyrogram.types import Message
from info import CHANNELS, ADMINS
from database.ia_filterdb import save_file

media_filter = filters.document | filters.video | filters.audio

if isinstance(CHANNELS, (int, str)):
    CHANNELS = [CHANNELS]

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def save_media(bot: Client, message: Message):
    media = None
    file_type = None

    for attr in ["document", "video", "audio"]:
        media = getattr(message, attr, None)
        if media:
            file_type = attr
            break

    if not media:
        return

    media.file_type = file_type
    media.caption = message.caption or ""
    await save_file(media)

@Client.on_message(filters.command("channel") & filters.user(ADMINS))
async def channel_info(bot: Client, message: Message):
    text_lines = ['📑 Indexed channels/groups\n']

    for channel_id in CHANNELS:
        try:
            chat = await bot.get_chat(channel_id)
            name = f"@{chat.username}" if chat.username else (chat.title or chat.first_name)
            text_lines.append(name)
        except Exception as e:
            text_lines.append(f"[Failed to fetch: {channel_id}]")  # Optional: Debug
            continue

    text_lines.append(f'\n\nTotal: {len(CHANNELS)}')
    text = "\n".join(text_lines)

    if len(text) <= 4096:
        await message.reply(text)
    else:
        filename = 'Indexed_Channels.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)
        await message.reply_document(filename)
        os.remove(filename)
