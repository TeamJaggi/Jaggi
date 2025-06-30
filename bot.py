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
users_data = {}  # Structure: {user_id: {"sources": [], "targets": [], "replacements": {}, "forwarding_active": False}}

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
        "Hi! I'm your auto-forwarder bot. 😄\n"
        "Use /forward to start forwarding messages from public channels. "
        "Add public channels with /addsource (e.g., @ChannelName)."
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
        await update.message.reply_text("Please provide a public channel username. E.g., /addsource @ChannelName")
        return
    source = context.args[0]
    try:
        # Verify the channel is accessible and is a channel
        chat = await context.bot.get_chat(source)
        if chat.type == "channel":
            if source not in users_data[user_id]["sources"]:
                users_data[user_id]["sources"].append(source)
                await update.message.reply_text(f"Added source: {source}")
                logger.info(f"User {user_id} added source: {source}")
            else:
                await update.message.reply_text(f"Source {source} already exists.")
        else:
            await update.message.reply_text("The source must be a public channel.")
    except TelegramError as e:
        await update.message.reply_text(f"Error: Could not access {source}. Ensure it's a public channel. ({e})")
        logger.error(f"Failed to add source {source} for user {user_id}: {e}")

# Command: /addtarget
async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username or ID. E.g., /addtarget @ChannelName")
        return
    target = context.args[0]
    try:
        # Verify the bot has permission to send messages to the target
        chat = await context.bot.get_chat(target)
        if chat.type in ["channel", "group", "supergroup"]:
            if target not in users_data[user_id]["targets"]:
                users_data[user_id]["targets"].append(target)
                await update.message.reply_text(f"Added target: {target}")
                logger.info(f"User {user_id} added target: {target}")
            else:
                await update.message.reply_text(f"Target {target} already exists.")
        else:
            await update.message.reply_text("The target must be a channel or group.")
    except TelegramError as e:
        await update.message.reply_text(f"Error: Could not access {target}. Ensure the bot is added and has posting permissions. ({e})")
        logger.error(f"Failed to add target {target} for user {user_id}: {e}")

# Command: /removesource
async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    if not context.args:
        await update.message.reply_text("Please provide a channel username. E.g., /removesource @ChannelName")
        return
    source = context.args[0]
    if source in users_data[user_id]["sources"]:
        users_data[user_id]["sources"].remove(source)
        await update.message.reply_text(f"Removed source: {source}")
        logger.info(f"User {user_id} removed source: {source}")
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
        logger.info(f"User {user_id} removed target: {target}")
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
    logger.info(f"User {user_id} added replacement: {old_text} -> {new_text}")

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
        logger.info(f"User {user_id} removed replacement: {old_text}")
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
    logger.info(f"User {user_id} started forwarding")

# Command: /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    init_user_data(user_id)
    users_data[user_id]["forwarding_active"] = False
    await update.message.reply_text("Forwarding stopped.")
    logger.info(f"User {user_id} stopped forwarding")

# Handle incoming messages from source channels
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.channel_post:
        logger.debug("Received non-channel post update, ignoring")
        return

    channel_username = update.channel_post.chat.username
    channel_id = f"@{channel_username}" if channel_username else str(update.channel_post.chat.id)
    logger.debug(f"Received channel post from {channel_id}")

    message_text = update.channel_post.text or update.channel_post.caption or ""

    # Forward messages to users who have this channel as a source
    for user_id, data in users_data.items():
        if data["forwarding_active"] and channel_id in data["sources"]:
            modified_text = message_text
            for old, new in data["replacements"].items():
                modified_text = modified_text.replace(old, new)
                logger.debug(f"Applied replacement for user {user_id}: {old} -> {new}")

            # Forward to all target channels
            for target in data["targets"]:
                try:
                    if update.channel_post.photo:
                        await context.bot.send_photo(
                            chat_id=target,
                            photo=update.channel_post.photo[-1].file_id,
                            caption=modified_text,
                        )
                        logger.info(f"Forwarded photo from {channel_id} to {target} for user {user_id}")
                    elif update.channel_post.video:
                        await context.bot.send_video(
                            chat_id=target,
                            video=update.channel_post.video.file_id,
                            caption=modified_text,
                        )
                        logger.info(f"Forwarded video from {channel_id} to {target} for user {user_id}")
                    else:
                        await context.bot.send_message(
                            chat_id=target,
                            text=modified_text or "Forwarded message",
                        )
                        logger.info(f"Forwarded text from {channel_id} to {target} for user {user_id}")
                except TelegramError as e:
                    logger.error(f"Failed to forward to {target} for user {user_id}: {e}")

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    # Use environment variable for bot token
    token = '8103884844:AAE-67rbwRIjVu98GCg4TWPuxq2Yz9JdvrY'
    if not token:
        logger.error("BOT token is not set")
        raise ValueError("BOT token is not set")
    
    application = Application.builder().token(token).build()

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
