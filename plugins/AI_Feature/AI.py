import asyncio
from pyrogram import Client, filters
import aiohttp

@Client.on_message(filters.command("ai"))
async def lexica_askbot(client, message):
    query = " ".join(message.text.split()[1:])
    if not query:
        await message.reply_text("Please Enter Your Question ..!!\n\n<code>/ai Question</code>")
        return
    payload = {
        'messages': [
            {'role': "user", 'content': query},
        ],
        "model_id": 18
    }
    api = 'https://api.qewertyy.dev/models'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                result = data.get('content')
    except aiohttp.ClientError as e:
        result = f"Error: {e}"
    except ValueError:
        result = "Failed to parse response"
    await message.reply_text(f">**{result}**")
