import logging
import aiohttp
import asyncio
import signal
import pytz

from pyrogram import Client, __version__, types
from pyrogram.raw.all import layer
from database.ia_filterdb import Media, Media2, choose_mediaDB, db as clientDB
from database.users_chats_db import db
from info import SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, SECONDDB_URI
from utils import temp
from Script import script
from datetime import date, datetime
from plugins.webcode import bot_run
from aiohttp import web as webserver
from sample_info import tempDict
from typing import Union, Optional, AsyncGenerator

logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

class Bot(Client):

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=20,
        )
        self.keep_alive_task = None
        self.web_runner = None

    async def keep_alive(self):
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    await session.get("https://adequate-quail-filterbotkn-818b00d4.koyeb.app/")
                    logging.info("💚 Keep-alive ping successful.")
                except Exception as e:
                    logging.error(f"⚠️ Keep-alive failed: {e}")
                await asyncio.sleep(60)  # safer interval (instead of 4s)

    async def start(self):
        logging.info("🚀 Starting bot...")
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats

        await super().start()

        logging.info("📂 Ensuring database indexes...")
        await Media.ensure_indexes()
        await Media2.ensure_indexes()

        stats = await clientDB.command('dbStats')
        free_dbSize = round(512 - ((stats['dataSize'] / (1024 * 1024)) +
                                   (stats['indexSize'] / (1024 * 1024))), 2)

        if SECONDDB_URI and free_dbSize < 10:
            tempDict["indexDB"] = SECONDDB_URI
            logging.info(f"🗄️ Primary DB low ({free_dbSize} MB) → Switching to Secondary DB.")
        elif not SECONDDB_URI:
            logging.error("❌ Missing SECONDDB_URI! Exiting...")
            raise SystemExit
        else:
            logging.info(f"🗄️ Primary DB OK ({free_dbSize} MB). Using Primary DB.")

        await choose_mediaDB()

        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = f"@{me.username}"

        logging.info(
            f"🤖 Bot: {me.first_name} | Pyrogram v{__version__} "
            f"(Layer {layer}) | @{me.username}"
        )

        tz = pytz.timezone("Asia/Kolkata")
        today = date.today()
        now = datetime.now(tz)
        time_str = now.strftime("%I:%M:%S %p")

        await self.send_message(
            chat_id=LOG_CHANNEL,
            text=script.RESTART_TXT.format(today, time_str),
        )

        logging.info("🌐 Starting keep-alive task...")
        self.keep_alive_task = asyncio.create_task(self.keep_alive())

        app_web = await bot_run()
        self.web_runner = webserver.AppRunner(app_web)
        await self.web_runner.setup()
        await webserver.TCPSite(self.web_runner, "0.0.0.0", 8080).start()
        logging.info("✅ Web server running on port 8080.")

    async def stop(self, *args):
        logging.info("🛑 Stopping bot...")
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            logging.info("💤 Keep-alive stopped.")
        if self.web_runner:
            await self.web_runner.cleanup()
            logging.info("💤 Web server stopped.")
        await super().stop()
        logging.info("👋 Bot stopped cleanly.")

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while current < limit:
            new_diff = min(200, limit - current)
            messages = await self.get_messages(
                chat_id, list(range(current, current + new_diff))
            )
            for message in messages:
                if message:
                    yield message
            current += new_diff


app = Bot()
loop = asyncio.get_event_loop()

for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.stop()))
    except NotImplementedError:
        pass

app.run()
