import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import re

API_ID = 24500851  # your API_ID from https://my.telegram.org
API_HASH = "4e1329c4610258e6fb2c271a337f8b3c"
BOT_TOKEN = "8103884844:AAE-67rbwRIjVu98GCg4TWPuxq2Yz9JdvrY"

# Storage
forwarding = {}      # user_id: bool
sources = {}         # user_id: [source_channel_usernames]
targets = {}         # user_id: [target_channel_ids]
replacements = {}    # user_id: [(from_text, to_text)]

app = Client("autoforwardbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Command: /start
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        "**✅ I am alive!**\n\n"
        "Use /addsource, /addtarget, /forward to start forwarding.\n"
        "/settings to view config."
    )

# Command: /addsource
@app.on_message(filters.command("addsource"))
async def add_source(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("Usage: `/addsource source_channel_username`", quote=True)
    src = message.command[1]
    sources.setdefault(user, []).append(src)
    await message.reply(f"✅ Added source channel: `{src}`", quote=True)

# Command: /removesource
@app.on_message(filters.command("removesource"))
async def remove_source(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("Usage: `/removesource source_channel_username`", quote=True)
    src = message.command[1]
    if user in sources and src in sources[user]:
        sources[user].remove(src)
        await message.reply(f"✅ Removed source: `{src}`")
    else:
        await message.reply("❌ Source not found.")

# Command: /addtarget
@app.on_message(filters.command("addtarget"))
async def add_target(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("Usage: `/addtarget target_channel_id`", quote=True)
    tgt = int(message.command[1])
    targets.setdefault(user, []).append(tgt)
    await message.reply(f"✅ Added target channel ID: `{tgt}`")

# Command: /removetarget
@app.on_message(filters.command("removetarget"))
async def remove_target(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("Usage: `/removetarget target_channel_id`", quote=True)
    tgt = int(message.command[1])
    if user in targets and tgt in targets[user]:
        targets[user].remove(tgt)
        await message.reply(f"✅ Removed target: `{tgt}`")
    else:
        await message.reply("❌ Target not found.")

# Command: /replace
@app.on_message(filters.command("replace"))
async def add_replace(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 3:
        return await message.reply("Usage: `/replace from_text to_text`", quote=True)
    frm = message.command[1]
    to = message.command[2]
    replacements.setdefault(user, []).append((frm, to))
    await message.reply(f"✅ Replacement added: `{frm}` → `{to}`")

# Command: /removereplace
@app.on_message(filters.command("removereplace"))
async def remove_replace(client, message: Message):
    user = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("Usage: `/removereplace from_text`", quote=True)
    frm = message.command[1]
    if user in replacements:
        before = len(replacements[user])
        replacements[user] = [pair for pair in replacements[user] if pair[0] != frm]
        after = len(replacements[user])
        if before != after:
            await message.reply(f"✅ Removed replacements for `{frm}`")
        else:
            await message.reply("❌ Replacement not found.")
    else:
        await message.reply("❌ No replacements set.")

# Command: /forward
@app.on_message(filters.command("forward"))
async def start_forward(client, message: Message):
    user = message.from_user.id
    forwarding[user] = True
    await message.reply("🚀 **Forwarding started!** I will copy new messages.")

# Command: /stop
@app.on_message(filters.command("stop"))
async def stop_forward(client, message: Message):
    user = message.from_user.id
    forwarding[user] = False
    await message.reply("🛑 **Forwarding stopped.**")

# Command: /settings
@app.on_message(filters.command("settings"))
async def settings(client, message: Message):
    user = message.from_user.id
    s = sources.get(user, [])
    t = targets.get(user, [])
    r = replacements.get(user, [])
    f = forwarding.get(user, False)
    rep = "\n".join([f"- `{x}` → `{y}`" for x, y in r]) or "None"
    await message.reply(
        f"**⚙️ Settings:**\n\n"
        f"**Forwarding:** {f}\n"
        f"**Sources:** {s}\n"
        f"**Targets:** {t}\n"
        f"**Replacements:**\n{rep}"
    )

# Auto-forward handler
@app.on_message(filters.channel)
async def forward_handler(client, message: Message):
    # For each user with forwarding on
    for user, is_on in forwarding.items():
        if not is_on:
            continue
        user_sources = sources.get(user, [])
        user_targets = targets.get(user, [])
        if message.chat.username not in user_sources:
            continue

        text = message.text or message.caption or ""
        # Apply replacements
        for frm, to in replacements.get(user, []):
            text = re.sub(re.escape(frm), to, text)

        # Forward to each target
        for tgt in user_targets:
            if message.text:
                await client.send_message(tgt, text)
            elif message.caption and message.photo:
                await client.send_photo(tgt, photo=message.photo.file_id, caption=text)
            elif message.caption and message.video:
                await client.send_video(tgt, video=message.video.file_id, caption=text)
            else:
                await message.copy(tgt)

app.run()
