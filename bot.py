import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage (replace with a database for production)
users_data = {}  # Structure: {user_id: {"sources": [], "targets": [], "replacements": {}}}

# Initialize user data
def init_user_data(user_id):
    if user_id not in users_data:
        users_data[user_id] = {
            "sources": [],
            "targets": [],
            "replacements": {},
            "forwarding_active": False,
        }

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    await update.message.reply_text(
        "Hi! I'm your auto-forwarder bot. I'm alive! 😄\n"
        "Use /forward to start forwarding, /settings to configure, or check other commands."
    )

# Command: /settings
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    user_data = users_data[user_id]
    settings_text = (
        f"📜 Current Settings:\n"
        f"Sources: {', '.join(user_data['sources']) or 'None'}\n"
        f"Targets: {', '.join(user_data['targets']) or 'None'}\n"
        f"Replacements: {', '.join([f'{k} -> {v}' for k, v in user_data['replacements'].items()]) or 'None'}\n"
        f"Forwarding: {'Active' if user_data['forwarding_active'] else 'Inactive'}"
    )
    await update.message.reply_text(settings_text)

# Command: /addsource
async def add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username or ID. E.g., /addsource @ChannelName")
        return
    source = context.args[0]
    if source not in users_data[user_id]["sources"]:
        users_data[user_id]["sources"].append(source)
        await update.message.reply_text(f"Added source: {source}")
    else:
        await update.message.reply_text(f"Source {source} already exists.")

# Command: /addtarget
async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username or ID. E.g., /addtarget @ChannelName")
        return
    target = context.args[0]
    if target not in users_data[user_id]["targets"]:
        users_data[user_id]["targets"].append(target)
        await update.message.reply_text(f"Added target: {target}")
    else:
        await update.message.reply_text(f"Target {target} already exists.")

# Command: /removesource
async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username or ID. E.g., /removesource @ChannelName")
        return
    source = context.args[0]
    if source in users_data[user_id]["sources"]:
        users_data[user_id]["sources"].remove(source)
        await update.message.reply_text(f"Removed source: {source}")
    else:
        await update.message.reply_text(f"Source {source} not found.")

# Command: /removetarget
async def remove_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username or ID. E.g., /removetarget @ChannelName")
        return
    target = context.args[0]
    if target in users_data[user_id]["targets"]:
        users_data[user_id]["targets"].remove(target)
        await update.message.reply_text(f"Removed target: {target}")
    else:
        await update.message.reply_text(f"Target {target} not found.")

# Command: /replace
async def replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if len(context.args) < 2:
        await update.message.reply_text("Please provide text to replace and replacement. E.g., /replace old new")
        return
    old_text, new_text = context.args[0], context.args[1]
    users_data[user_id]["replacements"][old_text] = new_text
    await update.message.reply_text(f"Added replacement: '{old_text}' -> '{new_text}'")

# Command: /removereplace
async def remove_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide text to remove. E.g., /removereplace old")
        return
    old_text = context.args[0]
    if old_text in users_data[user_id]["replacements"]:
        del users_data[user_id]["replacements"][old_text]
        await update.message.reply_text(f"Removed replacement for: {old_text}")
    else:
        await update.message.reply_text(f"Replacement for '{old_text}' not found.")

# Command: /forward
async def forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not users_data[user_id]["sources"] or not users_data[user_id]["targets"]:
        await update.message.reply_text("Please add at least one source and one target channel using /addsource and /addtarget.")
        return
    users_data[user_id]["forwarding_active"] = True
    await update.message.reply_text("Forwarding started! Messages from source channels will be forwarded to target channels.")

# Command: /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    users_data[user_id]["forwarding_active"] = False
    await update.message.reply_text("Forwarding stopped.")

# Handle incoming messages from source channels
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    # Check if the message is from a channel
    if update.channel_post:
        channel_id = str(update.channel_post.chat.id)
        message_text = update.channel_post.text or update.channel_post.caption or ""

        # Apply replacements
        for user_id, data in users_data.items():
            if data["forwarding_active"] and channel_id in data["sources"]:
                modified_text = message_text
                for old, new in data["replacements"].items():
                    modified_text = modified_text.replace(old, new)

                # Forward to all target channels
                for target in data["targets"]:
                    try:
                        if update.channel_post.photo:
                            await context.bot.send_photo(
                                chat_id=target,
                                photo=update.channel_post.photo[-1].file_id,
                                caption=modified_text,
                            )
                        elif update.channel_post.video:
                            await context.bot.send_video(
                                chat_id=target,
                                video=update.channel_post.video.file_id,
                                caption=modified_text,
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=target,
                                text=modified_text or "Forwarded message",
                            )
                    except TelegramError as e:
                        logger.error(f"Failed to forward to {target}: {e}")

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    # Replace 'YOUR_BOT_TOKEN' with your actual bot token
    application = Application.builder().token('8103884844:AAE-67rbwRIjVu98GCg4TWPuxq2Yz9JdvrY').build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("addsource", add_source))
    application.add_handler(CommandHandler("addtarget", add_target))
    application.add_handler(CommandHandler("removesource", remove_source))
    application.add_handler(CommandHandler("removetarget", remove_target))
    application.add_handler(CommandHandler("replace", replace))
    application.add_handler(CommandHandler("removereplace", remove_replace))
    application.add_handler(CommandHandler("forward", forward))
    application.add_handler(CommandHandler("stop", stop))

    # Add message handler for channel posts
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_message))

    # Add error handler
    application.add_error_handler(error_handler)

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()
