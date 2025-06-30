import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aiohttp import web
import re
import nest_asyncio
from pyngrok import ngrok

# Configuration
YOUR_BOT_TOKEN = "8103884844:AAE-67rbwRIjVu98GCg4TWPuxq2Yz9JdvrY"  # Replace with your bot token
YOUR_NGROK_TOKEN = "2zDBBUGjp433mqHglop31lwpFpb_2bWTSpJ23fyZZBc5hWxQB"  # Remember to revoke and regenerate this!
WEBHOOK_PORT = 8443  # Can be changed if needed

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot data storage
class BotData:
    def __init__(self):
        self.user_sources = {}  # {user_id: [source_channel_ids]}
        self.user_targets = {}  # {user_id: [target_channel_ids]}
        self.replacements = {}  # {user_id: {"from_text": "to_text"}}
        self.active_forwards = set()  # user_ids with active forwarding

bot_data = BotData()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your Auto Forwarder Bot.\n\n"
        "📚 Available commands:\n"
        "⏣ /start - check I'm alive\n"
        "⏣ /forward - forward messages\n"
        "⏣ /settings - configure your settings\n"
        "⏣ /stop - stop your ongoing forwarding\n"
        "⏣ /replace - for text or link replacements\n"
        "⏣ /addsource - for adding source channel\n"
        "⏣ /addtarget - for adding target channel\n"
        "⏣ /removetarget - for removing target channel\n"
        "⏣ /removesource - for removing source channel\n"
        "⏣ /removereplace - to remove word which was add earlier to replace\n\n"
        "💢 Features:\n"
        "► Forward message from public channel to your channel without admin permission in source channel."
    )

async def forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in bot_data.user_sources or not bot_data.user_sources[user_id]:
        await update.message.reply_text("Please add source channels first using /addsource")
        return
    
    if user_id not in bot_data.user_targets or not bot_data.user_targets[user_id]:
        await update.message.reply_text("Please add target channels first using /addtarget")
        return
    
    bot_data.active_forwards.add(user_id)
    await update.message.reply_text("Forwarding started! I'll now forward messages from your source channels to target channels.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id in bot_data.active_forwards:
        bot_data.active_forwards.remove(user_id)
        await update.message.reply_text("Forwarding stopped!")
    else:
        await update.message.reply_text("No active forwarding to stop.")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    sources = bot_data.user_sources.get(user_id, [])
    targets = bot_data.user_targets.get(user_id, [])
    replacements = bot_data.replacements.get(user_id, {})
    
    message = "⚙️ Your Settings:\n\n"
    message += f"🔹 Source channels: {len(sources)}\n"
    message += f"🔹 Target channels: {len(targets)}\n"
    message += f"🔹 Text replacements: {len(replacements)}\n"
    message += f"🔹 Forwarding status: {'Active' if user_id in bot_data.active_forwards else 'Inactive'}"
    
    await update.message.reply_text(message)

async def add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide a source channel ID or username. Usage: /addsource @channel_name")
        return
    
    source = context.args[0].strip()
    
    if user_id not in bot_data.user_sources:
        bot_data.user_sources[user_id] = []
    
    if source not in bot_data.user_sources[user_id]:
        bot_data.user_sources[user_id].append(source)
        await update.message.reply_text(f"Source channel {source} added successfully!")
    else:
        await update.message.reply_text(f"Source channel {source} is already in your list.")

async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide a target channel ID or username. Usage: /addtarget @channel_name")
        return
    
    target = context.args[0].strip()
    
    if user_id not in bot_data.user_targets:
        bot_data.user_targets[user_id] = []
    
    if target not in bot_data.user_targets[user_id]:
        bot_data.user_targets[user_id].append(target)
        await update.message.reply_text(f"Target channel {target} added successfully!")
    else:
        await update.message.reply_text(f"Target channel {target} is already in your list.")

async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide a source channel ID or username to remove. Usage: /removesource @channel_name")
        return
    
    source = context.args[0].strip()
    
    if user_id in bot_data.user_sources and source in bot_data.user_sources[user_id]:
        bot_data.user_sources[user_id].remove(source)
        await update.message.reply_text(f"Source channel {source} removed successfully!")
    else:
        await update.message.reply_text(f"Source channel {source} not found in your list.")

async def remove_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide a target channel ID or username to remove. Usage: /removetarget @channel_name")
        return
    
    target = context.args[0].strip()
    
    if user_id in bot_data.user_targets and target in bot_data.user_targets[user_id]:
        bot_data.user_targets[user_id].remove(target)
        await update.message.reply_text(f"Target channel {target} removed successfully!")
    else:
        await update.message.reply_text(f"Target channel {target} not found in your list.")

async def add_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text("Please provide text to replace and replacement text. Usage: /replace old_text new_text")
        return
    
    from_text = ' '.join(context.args[:-1])
    to_text = context.args[-1]
    
    if user_id not in bot_data.replacements:
        bot_data.replacements[user_id] = {}
    
    bot_data.replacements[user_id][from_text] = to_text
    await update.message.reply_text(f"Replacement added: '{from_text}' will be replaced with '{to_text}'")

async def remove_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Please provide text to remove from replacements. Usage: /removereplace text_to_remove")
        return
    
    text_to_remove = ' '.join(context.args)
    
    if user_id in bot_data.replacements and text_to_remove in bot_data.replacements[user_id]:
        del bot_data.replacements[user_id][text_to_remove]
        await update.message.reply_text(f"Replacement for '{text_to_remove}' removed successfully!")
    else:
        await update.message.reply_text(f"No replacement found for '{text_to_remove}'")

async def handle_webhook(request):
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    return web.Response()

async def setup_webhook():
    """Configure ngrok and set up webhook"""
    # Authenticate ngrok
    ngrok.set_auth_token(YOUR_NGROK_TOKEN)
    
    # Create ngrok tunnel
    tunnel = ngrok.connect(WEBHOOK_PORT, bind_tls=True)
    webhook_url = f"{tunnel.public_url}/webhook"
    
    # Set webhook in Telegram
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook URL: {webhook_url}")
    return webhook_url

async def on_startup(app):
    """Run when application starts"""
    await setup_webhook()

if __name__ == '__main__':
    # Create Application
    application = Application.builder().token(YOUR_BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("forward", forward))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("addsource", add_source))
    application.add_handler(CommandHandler("addtarget", add_target))
    application.add_handler(CommandHandler("removesource", remove_source))
    application.add_handler(CommandHandler("removetarget", remove_target))
    application.add_handler(CommandHandler("replace", add_replace))
    application.add_handler(CommandHandler("removereplace", remove_replace))

    # Create aiohttp app
    app = web.Application()
    app.router.add_post('/webhook', handle_webhook)
    app.on_startup.append(on_startup)
    
    # Enable nested asyncio if needed
    nest_asyncio.apply()
    
    # Start the server
    logger.info("Starting web server...")
    web.run_app(
        app,
        port=WEBHOOK_PORT,
        access_log=None,  # Disable aiohttp access logs
        handle_signals=True
    )
