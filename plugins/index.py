import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] 🔹 %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

lock = asyncio.Lock()


@Client.on_callback_query(filters.regex(r"^index"))
async def index_files(bot, query):
    if query.data.startswith("index_cancel"):
        temp.CANCEL = True
        await query.answer("❌ Cancelling Indexing...", show_alert=True)
        return

    _, action, chat, last_msg_id, from_user = query.data.split("#")

    if action == "reject":
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f"⚠️ Your indexing request for `{chat}` has been declined by moderators.",
            reply_to_message_id=int(last_msg_id)
        )
        return

    if lock.locked():
        return await query.answer("⏳ Another process is running, please wait...", show_alert=True)

    msg = query.message
    await query.answer("⚙️ Processing your request...", show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f"✅ Your request for indexing `{chat}` has been approved and will start shortly.",
            reply_to_message_id=int(last_msg_id)
        )

    await msg.edit(
        "🚀 Starting Indexing...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="index_cancel")]])
    )

    try:
        chat = int(chat)
    except ValueError:
        pass

    asyncio.create_task(index_files_to_db(int(last_msg_id), chat, msg, bot))
    logger.info(f"📥 Indexing started for chat: {chat} by user: {from_user}")


@Client.on_message(
    (filters.forwarded | (filters.regex(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text)
    & filters.private & filters.incoming
)
async def send_for_index(bot, message):
    try:
        regex = re.compile(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text or "")
        if not match and not message.forward_from_chat:
            return await message.reply("❌ Invalid link or message.")

        if match:
            chat_id = match.group(4)
            last_msg_id = int(match.group(5))
            if chat_id.isnumeric():
                chat_id = int("-100" + chat_id)
        else:
            last_msg_id = message.forward_from_message_id
            chat_id = message.forward_from_chat.username or message.forward_from_chat.id

        await bot.get_chat(chat_id)
        k = await bot.get_messages(chat_id, last_msg_id)
        if k.empty:
            return await message.reply("⚠️ Unable to access messages. Make sure I’m an admin in that chat.")

        if message.from_user.id in ADMINS:
            buttons = [
                [InlineKeyboardButton("✅ Yes", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="close_data")]
            ]
            return await message.reply(
                f"📂 Index this Channel/Group?\n\n"
                f"🔹 Chat ID / Username: `{chat_id}`\n"
                f"🔹 Last Message ID: `{last_msg_id}`\n\n"
                f"Use /setskip to set skip value.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            link = f"@{message.forward_from_chat.username}"

        buttons = [
            [InlineKeyboardButton("✅ Accept", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}")]
        ]

        await bot.send_message(
            LOG_CHANNEL,
            f"🆕 Index Request\n\n👤 By: {message.from_user.mention} (`{message.from_user.id}`)\n"
            f"🗂 Chat: `{chat_id}`\n📄 Last Msg ID: `{last_msg_id}`\n🔗 Invite: {link}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        await message.reply("✅ Request sent! Please wait for moderator approval ⏳")

    except Exception as e:
        logger.exception(e)
        await message.reply(f"⚠️ Error: `{e}`")


@Client.on_message(filters.command("setskip") & filters.user(ADMINS))
async def set_skip_number(_, message):
    if len(message.command) < 2:
        return await message.reply("⚙️ Usage: /setskip <number>")

    try:
        temp.CURRENT = int(message.command[1])
        await message.reply(f"✅ Successfully set skip number to `{temp.CURRENT}`")
    except ValueError:
        await message.reply("❌ Skip number must be an integer.")


async def index_files_to_db(last_msg_id, chat, msg, bot):
    total_files = duplicate = errors = deleted = no_media = unsupported = 0

    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False

            async for message in bot.iter_messages(chat, last_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(
                        f"❌ Indexing Cancelled!\n\n"
                        f"📦 Saved: `{total_files}`\n⚙️ Duplicates: `{duplicate}`\n"
                        f"🗑 Deleted: `{deleted}`\n📄 Non-media: `{no_media + unsupported}`\n⚠️ Errors: `{errors}`"
                    )
                    logger.info("🛑 Indexing cancelled by user.")
                    break

                current += 1

                if current % 80 == 0:
                    await msg.edit_text(
                        f"⚙️ Progress Update\n\n"
                        f"📬 Fetched: `{current}`\n✅ Saved: `{total_files}`\n"
                        f"⚙️ Duplicates: `{duplicate}`\n🗑 Deleted: `{deleted}`\n"
                        f"📄 Non-media: `{no_media + unsupported}`\n⚠️ Errors: `{errors}`",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="index_cancel")]])
                    )

                if message.empty:
                    deleted += 1
                    continue
                elif not message.media:
                    no_media += 1
                    continue
                elif message.media not in [
                    enums.MessageMediaType.VIDEO,
                    enums.MessageMediaType.DOCUMENT
                ]:
                    unsupported += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                media.file_type = message.media.value
                media.caption = message.caption

                success, status = await save_file(bot, media)
                if success:
                    total_files += 1
                elif status == 0:
                    duplicate += 1
                elif status == 2:
                    errors += 1

            await msg.edit(
                f"✅ Indexing Complete!\n\n"
                f"📦 Total Saved: `{total_files}`\n⚙️ Duplicates: `{duplicate}`\n"
                f"🗑 Deleted: `{deleted}`\n📄 Non-media: `{no_media + unsupported}`\n⚠️ Errors: `{errors}`"
            )
            logger.info(f"✅ Indexing completed for chat {chat} with {total_files} files saved.")

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"⚠️ Error occurred: `{e}`")
