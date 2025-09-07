import logging
import asyncio
import sqlite3
import random
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from telegram.error import BadRequest, TelegramError
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
from telethon import events
import aiosqlite
import phonenumbers
from typing import Dict, Any, List, Tuple
import json

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
PHONE, OTP, FORWARD_SOURCE, FORWARD_TARGET, FORWARD_REPLACEMENTS = range(5)

class FixedAutoForwardBot:
    def __init__(self, bot_token: str, owner_id: int, api_id: int, api_hash: str, sms_service=None):
        self.bot_token = bot_token
        self.owner_id = owner_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.sms_service = sms_service
        self.application = Application.builder().token(bot_token).build()
        self.user_sessions: Dict[int, Dict[str, Any]] = {}
        self.user_clients: Dict[int, TelegramClient] = {}
        self.forwarding_tasks: Dict[int, asyncio.Task] = {}
        
        # Setup handlers
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup all message handlers"""
        # Conversation handler for setup process
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start), CommandHandler('setup', self.setup)],
            states={
                PHONE: [MessageHandler(filters.CONTACT, self.handle_contact)],
                OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.verify_otp)],
                FORWARD_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_forward_source)],
                FORWARD_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_forward_target)],
                FORWARD_REPLACEMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_forward_replacements)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("add_forward", self.add_forward))
        self.application.add_handler(CommandHandler("list_rules", self.list_rules))
        self.application.add_handler(CommandHandler("stop_forward", self.stop_forward))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast, filters.User(user_id=self.owner_id)))
        self.application.add_handler(CommandHandler("stats", self.stats, filters.User(user_id=self.owner_id)))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
    async def init_db(self):
        """Initialize database connection"""
        self.db = await aiosqlite.connect('forward_bot.db')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                phone TEXT UNIQUE,
                session_string TEXT,
                is_verified BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT,
                otp_code TEXT,
                expires_at DATETIME,
                is_used BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS forwarding_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                source_channel TEXT,
                target_channel TEXT,
                replacement_rules TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        await self.db.commit()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send welcome message and start setup process"""
        user_id = update.effective_user.id
        
        welcome_text = """
🤖 **Auto Forward Bot** 🤖

I can help you automatically forward messages from any source channel to your target channel.

**Features:**
- 🔄 Auto-forwarding from any source to your channel
- 🔧 Text and link replacement
- 🔒 Secure OTP authentication
- ⚡ Easy setup

Use /setup to verify your account and get started.
        """
        
        await update.message.reply_text(welcome_text)
        
        # Check if user is already verified
        async with self.db.execute("SELECT is_verified FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if user and user[0]:
            await update.message.reply_text(
                "Your account is already verified! Use /add_forward to set up forwarding rules."
            )
            return ConversationHandler.END
        
        # Request phone number
        keyboard = [[InlineKeyboardButton("📱 Share Phone Number", request_contact=True)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "To verify your account, please share your phone number:",
            reply_markup=reply_markup
        )
        
        # Initialize user session
        self.user_sessions[user_id] = {"step": PHONE}
        
        return PHONE
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        help_text = """
🤖 **Auto Forward Bot - Help** 🤖

**Available Commands:**
/setup - Verify your account with OTP
/add_forward - Set up a new forwarding rule
/list_rules - View your current forwarding rules
/stop_forward [id] - Stop a specific forwarding rule
/help - Show this help message

**How to set up forwarding:**
1. Use /setup to verify your account with OTP
2. Use /add_forward to create a forwarding rule
3. Provide source channel (where to forward from)
4. Provide target channel (where to forward to)
5. Optionally add text replacement rules

**Replacement Rules Format:**
`original_text->replacement_text, another_text->another_replacement`

**Example:**
`telegram->signal, example.com->mysite.com`
        """
        await update.message.reply_text(help_text)
    
    async def setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start setup process directly"""
        return await self.start(update, context)
    
    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle contact sharing"""
        user_id = update.effective_user.id
        phone_number = update.message.contact.phone_number
        
        # Validate and format phone number
        try:
            parsed_number = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed_number):
                await update.message.reply_text("❌ Invalid phone number. Please share a valid phone number.")
                return PHONE
                
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except:
            await update.message.reply_text("❌ Invalid phone number format. Please try again.")
            return PHONE
        
        # Store phone number in database
        await self.db.execute(
            "INSERT OR REPLACE INTO users (user_id, phone) VALUES (?, ?)",
            (user_id, formatted_number)
        )
        await self.db.commit()
        
        # Generate OTP
        otp = str(random.randint(100000, 999999))
        expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Store OTP in database
        await self.db.execute(
            "INSERT INTO otps (user_id, phone, otp_code, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, formatted_number, otp, expires_at)
        )
        await self.db.commit()
        
        # Send OTP via SMS (if service available) or via message
        if self.sms_service:
            try:
                await self.sms_service.send_sms(formatted_number, f"Your verification code is: {otp}")
                await update.message.reply_text(
                    f"✅ OTP sent to {formatted_number}. Please enter the code within 10 minutes."
                )
            except Exception as e:
                logger.error(f"SMS sending failed: {e}")
                await update.message.reply_text(
                    f"❌ Failed to send SMS. Your OTP is: {otp}. Please enter this code."
                )
        else:
            await update.message.reply_text(
                f"📋 Your OTP is: {otp}. Please enter this code within 10 minutes."
            )
        
        # Update user session
        self.user_sessions[user_id] = {
            "step": OTP,
            "phone": formatted_number
        }
        
        return OTP
    
    async def verify_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify OTP code and create user session"""
        user_id = update.effective_user.id
        otp_code = update.message.text.strip()
        
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != OTP:
            await update.message.reply_text("❌ Please start the verification process with /setup")
            return ConversationHandler.END
        
        # Verify OTP
        async with self.db.execute(
            "SELECT otp_code, expires_at FROM otps WHERE user_id = ? AND is_used = 0 ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ) as cursor:
            otp_data = await cursor.fetchone()
        
        if not otp_data:
            await update.message.reply_text("❌ No OTP found. Please start over with /setup")
            return ConversationHandler.END
        
        stored_otp, expires_at = otp_data
        
        if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
            await update.message.reply_text("❌ OTP has expired. Please request a new one with /setup")
            return ConversationHandler.END
        
        if otp_code == stored_otp:
            # Mark OTP as used and verify user
            await self.db.execute(
                "UPDATE otps SET is_used = 1 WHERE user_id = ? AND otp_code = ?",
                (user_id, otp_code)
            )
            await self.db.execute(
                "UPDATE users SET is_verified = 1 WHERE user_id = ?",
                (user_id,)
            )
            await self.db.commit()
            
            # Create Telethon client for user
            client = TelegramClient(StringSession(), self.api_id, self.api_hash)
            
            try:
                # Connect and authenticate with user's phone number
                await client.connect()
                
                # Send code request
                sent = await client.send_code_request(self.user_sessions[user_id]["phone"])
                
                # Sign in with the code
                await client.sign_in(self.user_sessions[user_id]["phone"], otp_code)
                
                # Save session string
                session_string = client.session.save()
                await self.db.execute(
                    "UPDATE users SET session_string = ? WHERE user_id = ?",
                    (session_string, user_id)
                )
                await self.db.commit()
                
                # Store client for later use
                self.user_clients[user_id] = client
                
                await update.message.reply_text(
                    "✅ Account verified successfully!\n\n"
                    "Now you can set up auto-forwarding using /add_forward command."
                )
                
            except Exception as e:
                logger.error(f"Error creating user session: {e}")
                await update.message.reply_text(
                    "❌ Error verifying your account. Please try again with /setup."
                )
                return OTP
            
            # Clear user session
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
                
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Invalid OTP. Please try again.")
            return OTP
    
    async def add_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new forwarding rule"""
        user_id = update.effective_user.id
        
        # Check if user is verified
        async with self.db.execute("SELECT is_verified, session_string FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or not user[0]:
            await update.message.reply_text("❌ Please verify your account first using /setup")
            return
        
        # Check if we have a valid session
        if user_id not in self.user_clients or not self.user_clients[user_id].is_connected():
            try:
                # Recreate client from session string
                session_string = user[1]
                if not session_string:
                    await update.message.reply_text("❌ Session expired. Please verify again with /setup.")
                    return
                    
                client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                await client.connect()
                
                # Test the connection
                await client.get_me()
                
                self.user_clients[user_id] = client
            except Exception as e:
                logger.error(f"Error reconnecting user session: {e}")
                await update.message.reply_text(
                    "❌ Error accessing your account. Please verify again with /setup."
                )
                return
        
        # Initialize forwarding setup in user session
        self.user_sessions[user_id] = {
            "step": FORWARD_SOURCE,
            "forwarding_rule": {}
        }
        
        await update.message.reply_text(
            "Please provide the source channel username or ID (e.g., @sourcechannel or -1001234567890):\n\n"
            "💡 Make sure you have joined this channel and have reading permissions."
        )
    
    async def handle_forward_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle source channel input"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != FORWARD_SOURCE:
            await update.message.reply_text("❌ Please start over with /add_forward")
            return ConversationHandler.END
        
        source_channel = update.message.text.strip()
        
        # Validate that user has access to source channel
        try:
            client = self.user_clients[user_id]
            entity = await client.get_entity(source_channel)
            
            # Check if user has permission to read from this channel
            try:
                messages = await client.get_messages(entity, limit=1)
                if not messages:
                    await update.message.reply_text(
                        "❌ You don't have access to this channel or it's empty. "
                        "Please make sure you've joined the channel and have reading permissions."
                    )
                    return FORWARD_SOURCE
            except Exception as e:
                await update.message.reply_text(
                    "❌ You don't have access to this channel. "
                    "Please make sure you've joined the channel and have reading permissions."
                )
                return FORWARD_SOURCE
                
        except Exception as e:
            logger.error(f"Error validating source channel: {e}")
            await update.message.reply_text(
                "❌ Invalid channel or you don't have access to it. "
                "Please provide a valid channel username or ID that you have access to."
            )
            return FORWARD_SOURCE
        
        self.user_sessions[user_id]["forwarding_rule"]["source"] = source_channel
        self.user_sessions[user_id]["step"] = FORWARD_TARGET
        
        await update.message.reply_text(
            "Now please provide the target channel username or ID (e.g., @targetchannel or -1001234567890):\n\n"
            "💡 Make sure you are an admin in this channel with posting permissions."
        )
        
        return FORWARD_TARGET
    
    async def handle_forward_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle target channel input"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != FORWARD_TARGET:
            await update.message.reply_text("❌ Please start over with /add_forward")
            return ConversationHandler.END
        
        target_channel = update.message.text.strip()
        
        # Validate that user has admin access to target channel
        try:
            client = self.user_clients[user_id]
            entity = await client.get_entity(target_channel)
            
            # Check if user has permission to send messages to this channel
            try:
                # Try sending a test message (will be deleted immediately)
                message = await client.send_message(entity, "🔒 Testing permissions... (this message will be deleted)")
                await asyncio.sleep(1)
                await client.delete_messages(entity, message)
            except Exception as e:
                await update.message.reply_text(
                    "❌ You don't have admin permissions in this channel. "
                    "Please make sure you're an admin with posting permissions."
                )
                return FORWARD_TARGET
                
        except Exception as e:
            logger.error(f"Error validating target channel: {e}")
            await update.message.reply_text(
                "❌ Invalid channel or you don't have admin permissions. "
                "Please provide a valid channel username or ID where you have admin rights."
            )
            return FORWARD_TARGET
        
        self.user_sessions[user_id]["forwarding_rule"]["target"] = target_channel
        self.user_sessions[user_id]["step"] = FORWARD_REPLACEMENTS
        
        await update.message.reply_text(
            "Optional: Provide text replacement rules in the format 'old->new' separated by commas.\n"
            "Example: 'telegram->signal, example.com->mysite.com'\n\n"
            "Or type 'skip' to continue without replacements:"
        )
        
        return FORWARD_REPLACEMENTS
    
    async def handle_forward_replacements(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle replacement rules input and start forwarding"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != FORWARD_REPLACEMENTS:
            await update.message.reply_text("❌ Please start over with /add_forward")
            return ConversationHandler.END
        
        replacements_text = update.message.text.strip()
        forwarding_rule = self.user_sessions[user_id]["forwarding_rule"]
        
        # Save to database
        replacement_rules = None if replacements_text.lower() == 'skip' else replacements_text
        
        await self.db.execute(
            "INSERT INTO forwarding_rules (user_id, source_channel, target_channel, replacement_rules) VALUES (?, ?, ?, ?)",
            (user_id, forwarding_rule["source"], forwarding_rule["target"], replacement_rules)
        )
        await self.db.commit()
        
        # Start forwarding messages
        if user_id in self.forwarding_tasks:
            self.forwarding_tasks[user_id].cancel()
            
        self.forwarding_tasks[user_id] = asyncio.create_task(
            self.start_forwarding(user_id, forwarding_rule["source"], 
                                 forwarding_rule["target"], replacement_rules)
        )
        
        # Clear user session
        del self.user_sessions[user_id]
        
        await update.message.reply_text(
            f"✅ Forwarding rule added successfully!\n\n"
            f"📥 From: {forwarding_rule['source']}\n"
            f"📤 To: {forwarding_rule['target']}\n"
            f"🔧 Replacements: {replacement_rules or 'None'}\n\n"
            f"Auto-forwarding is now active. Use /list_rules to see all your rules."
        )
        
        return ConversationHandler.END
    
    async def start_forwarding(self, user_id: int, source_channel: str, target_channel: str, replacement_rules: str):
        """Start forwarding messages from source to target channel"""
        try:
            client = self.user_clients[user_id]
            
            # Parse replacement rules
            replacements = []
            if replacement_rules:
                for rule in replacement_rules.split(','):
                    if '->' in rule:
                        old, new = rule.split('->', 1)
                        replacements.append((old.strip(), new.strip()))
            
            @client.on(events.NewMessage(chats=source_channel))
            async def handler(event):
                try:
                    message = event.message
                    text = message.text or message.caption or ""
                    
                    # Apply text replacements
                    for old, new in replacements:
                        text = text.replace(old, new)
                    
                    # Forward the message with replacements
                    if message.media:
                        # Handle media messages
                        if text:
                            await client.send_file(target_channel, message.media, caption=text)
                        else:
                            await client.send_file(target_channel, message.media)
                    else:
                        # Handle text messages
                        await client.send_message(target_channel, text)
                    
                    logger.info(f"Forwarded message from {source_channel} to {target_channel}")
                    
                except Exception as e:
                    logger.error(f"Error forwarding message: {e}")
            
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Error in forwarding task for user {user_id}: {e}")
    
    async def list_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all forwarding rules for the user"""
        user_id = update.effective_user.id
        
        # Check if user is verified
        async with self.db.execute("SELECT is_verified FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or not user[0]:
            await update.message.reply_text("❌ Please verify your account first using /setup")
            return
        
        async with self.db.execute(
            "SELECT id, source_channel, target_channel, replacement_rules, is_active FROM forwarding_rules WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rules = await cursor.fetchall()
        
        if not rules:
            await update.message.reply_text("You don't have any forwarding rules set up yet. Use /add_forward to create one.")
            return
        
        rules_text = "📋 Your Forwarding Rules:\n\n"
        for rule_id, source, target, replacements, is_active in rules:
            status = "✅ Active" if is_active else "❌ Inactive"
            rules_text += f"🆔 Rule #{rule_id}: {source} → {target} ({status})\n"
            if replacements:
                rules_text += f"   🔧 Replacements: {replacements}\n"
            rules_text += "\n"
        
        await update.message.reply_text(rules_text)
    
    async def stop_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop a forwarding rule"""
        user_id = update.effective_user.id
        
        # Check if user is verified
        async with self.db.execute("SELECT is_verified FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or not user[0]:
            await update.message.reply_text("❌ Please verify your account first using /setup")
            return
        
        if not context.args:
            await update.message.reply_text("Please specify the rule ID to stop. Use /list_rules to see your rules.")
            return
        
        rule_id = context.args[0]
        
        async with self.db.execute(
            "UPDATE forwarding_rules SET is_active = 0 WHERE id = ? AND user_id = ?",
            (rule_id, user_id)
        ) as cursor:
            await self.db.commit()
            
            if cursor.rowcount > 0:
                await update.message.reply_text(f"✅ Forwarding rule #{rule_id} has been stopped.")
            else:
                await update.message.reply_text("❌ Rule not found or you don't have permission to modify it.")
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users (admin only)"""
        if not context.args:
            await update.message.reply_text("Please provide a message to broadcast. Example: /broadcast Hello everyone!")
            return
        
        message = " ".join(context.args)
        
        async with self.db.execute("SELECT user_id FROM users WHERE is_verified = 1") as cursor:
            users = await cursor.fetchall()
        
        success_count = 0
        fail_count = 0
        
        for (user_id,) in users:
            try:
                await context.bot.send_message(chat_id=user_id, text=f"📢 Announcement from admin:\n\n{message}")
                success_count += 1
                await asyncio.sleep(0.1)  # Rate limiting
            except (BadRequest, TelegramError) as e:
                logger.error(f"Failed to send broadcast to {user_id}: {e}")
                fail_count += 1
        
        await update.message.reply_text(
            f"✅ Broadcast completed:\n"
            f"✅ Successful: {success_count}\n"
            f"❌ Failed: {fail_count}"
        )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics (admin only)"""
        async with self.db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with self.db.execute("SELECT COUNT(*) FROM users WHERE is_verified = 1") as cursor:
            verified_users = (await cursor.fetchone())[0]
        
        async with self.db.execute("SELECT COUNT(*) FROM forwarding_rules") as cursor:
            total_rules = (await cursor.fetchone())[0]
        
        async with self.db.execute("SELECT COUNT(*) FROM forwarding_rules WHERE is_active = 1") as cursor:
            active_rules = (await cursor.fetchone())[0]
        
        stats_text = (
            f"🤖 Bot Statistics:\n\n"
            f"👥 Users: {total_users} total, {verified_users} verified\n"
            f"🔄 Forwarding Rules: {total_rules} total, {active_rules} active\n"
        )
        
        await update.message.reply_text(stats_text)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the current operation"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Add button handlers if needed
    
    async def run(self):
        """Run the bot with fixed initialization"""
        await self.init_db()
        
        # Load existing user sessions
        async with self.db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL AND is_verified = 1") as cursor:
            users = await cursor.fetchall()
            
            for user_id, session_string in users:
                try:
                    client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                    await client.connect()
                    
                    # Test the connection
                    await client.get_me()
                    
                    self.user_clients[user_id] = client
                    logger.info(f"Restored session for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to restore session for user {user_id}: {e}")
        
        # Start the application
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot is now running...")
        
        # Keep the application running (FIXED: using asyncio.Event instead of idle())
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        
    async def shutdown(self):
        """Shutdown the bot gracefully"""
        # Disconnect all user clients
        for user_id, client in self.user_clients.items():
            if client.is_connected():
                await client.disconnect()
        
        # Cancel all forwarding tasks
        for task in self.forwarding_tasks.values():
            task.cancel()
        
        await self.application.stop()
        await self.application.shutdown()
        await self.db.close()

# Main execution
if __name__ == "__main__":
    # Replace with your actual values
    BOT_TOKEN = "7738808803:AAH7M8lNwGb5UAUHA0yl8-xvy-C3yZEJ7hc"  #  BotFather
    OWNER_ID = 6651946441  # Your Telegram user ID
    API_ID = 27631275  # Your Telegram API ID from https://my.telegram.org
    API_HASH = "d15c8c4c88a5b82aab6a673eff8ca244"  # Your Telegram API Hash
    
    # Optional: Configure SMS service for OTP delivery
    # SMS_SERVICE = SomeSmsService(api_key="your_api_key")
    SMS_SERVICE = None  # Set to None to send OTP via Telegram message
    
    bot = FixedAutoForwardBot(BOT_TOKEN, OWNER_ID, API_ID, API_HASH, SMS_SERVICE)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        asyncio.run(bot.shutdown())
