import logging
import asyncio
import sqlite3
import random
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from telegram.error import BadRequest, TelegramError
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipant, ChannelParticipantCreator, ChannelParticipantAdmin
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

class ManualPhoneAutoForwardBot:
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
        self.force_subscribe_channel = None
        
        # Setup handlers
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup all message handlers"""
        # Conversation handler for setup process
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start), CommandHandler('setup', self.setup_command)],
            states={
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_phone_input)],
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
        self.application.add_handler(CommandHandler("user_stats", self.user_stats, filters.User(user_id=self.owner_id)))
        self.application.add_handler(CommandHandler("set_force_subscribe", self.set_force_subscribe, filters.User(user_id=self.owner_id)))
        self.application.add_handler(CommandHandler("check_subscription", self.check_subscription))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
    async def init_db(self):
        """Initialize database connection"""
        self.db = await aiosqlite.connect('forward_bot.db', isolation_level=None)
        
        # Enable WAL mode for better concurrency
        await self.db.execute('PRAGMA journal_mode=WAL')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                phone TEXT UNIQUE,
                session_string TEXT,
                is_verified BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                has_subscribed BOOLEAN DEFAULT 0
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
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
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
                last_forwarded DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                message_id INTEGER,
                forwarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rule_id) REFERENCES forwarding_rules (id) ON DELETE CASCADE
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await self.db.commit()
        
        # Load force subscribe channel from database
        async with self.db.execute(
            "SELECT value FROM bot_settings WHERE key = 'force_subscribe_channel'"
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                self.force_subscribe_channel = result[0]
    
    async def check_user_subscription(self, user_id: int) -> bool:
        """Check if user has subscribed to the required channel"""
        if not self.force_subscribe_channel:
            return True
            
        async with self.db.execute(
            "SELECT has_subscribed FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result and result[0]:
                return True
                
        return False
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send welcome message and start setup process"""
        user_id = update.effective_user.id
        
        # Update user last active time
        await self.db.execute(
            "INSERT OR REPLACE INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)",
            (user_id,)
        )
        await self.db.commit()
        
        # Check if user needs to subscribe to channel
        if not await self.check_user_subscription(user_id):
            if self.force_subscribe_channel:
                await update.message.reply_text(
                    f"📢 Please join our channel first to use this bot:\n\n"
                    f"{self.force_subscribe_channel}\n\n"
                    "After joining, use /check_subscription to verify."
                )
                return ConversationHandler.END
        
        welcome_text = """
🤖 **Manual Phone Auto Forward Bot** 🤖

I can help you automatically forward messages from any source channel to your target channel.

**Features:**
- 🔄 Auto-forwarding from any source to your channel
- 🔧 Text and link replacement
- 🔒 Secure OTP authentication
- 📱 Manual phone number input
- ⚡ Easy setup

**Commands:**
/setup <phone> - Verify your account with phone number
/add_forward - Add a new forwarding rule
/list_rules - List your forwarding rules
/stop_forward - Stop a forwarding rule
/help - Show this help message

**Example:**
/setup +919876543210

To get started, use /setup with your phone number.
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
        
        return ConversationHandler.END
    
    async def setup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setup command with phone number"""
        user_id = update.effective_user.id
        
        # Check if user already verified
        async with self.db.execute("SELECT is_verified FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if user and user[0]:
            await update.message.reply_text("✅ Your account is already verified! Use /add_forward to set up forwarding rules.")
            return ConversationHandler.END
        
        # Check if phone number provided
        if not context.args:
            await update.message.reply_text("❌ Please provide phone number. Example: /setup +919876543210")
            return
        
        phone_number = ' '.join(context.args).strip()
        
        # Validate phone number
        try:
            parsed_number = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed_number):
                await update.message.reply_text("❌ Invalid phone number. Please provide valid number.")
                return
                
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            logger.error(f"Phone number parsing error: {e}")
            await update.message.reply_text("❌ Invalid phone number format. Please try again.")
            return
        
        # Check if this phone number is already registered with another account
        async with self.db.execute("SELECT user_id FROM users WHERE phone = ? AND user_id != ?", 
                                  (formatted_number, user_id)) as cursor:
            existing_user = await cursor.fetchone()
            
        if existing_user:
            await update.message.reply_text(
                "❌ This phone number is already registered with another account. "
                "Please use a different phone number or contact support."
            )
            return
        
        # Store phone number in database
        await self.db.execute(
            "INSERT OR REPLACE INTO users (user_id, phone, last_active) VALUES (?, ?, CURRENT_TIMESTAMP)",
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
        
        # Send OTP via Telegram (user ke account par)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔐 Your OTP code is: {otp}\n\n"
                     f"Please enter this code in the bot within 10 minutes.\n\n"
                     f"💡 Tip: Enter each digit separately like: 1 2 3 4 5 6"
            )
            
            await update.message.reply_text(
                f"✅ OTP sent to your Telegram account!\n\n"
                f"Please check your Telegram messages and enter the OTP code."
            )
            
            # User session mein OTP step set karein
            self.user_sessions[user_id] = {
                "step": OTP,
                "phone": formatted_number,
                "otp_expected": otp
            }
            
            return OTP
            
        except Exception as e:
            logger.error(f"OTP send karne mein error: {e}")
            await update.message.reply_text(
                "❌ Error sending OTP. Please try again later."
            )
            return ConversationHandler.END
    
    async def handle_phone_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle phone number input from conversation"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != PHONE:
            await update.message.reply_text("Please start the verification process with /setup")
            return ConversationHandler.END
        
        phone_number = update.message.text.strip()
        
        # Validate and format phone number
        try:
            parsed_number = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed_number):
                await update.message.reply_text("❌ Invalid phone number. Please share a valid phone number.")
                return PHONE
                
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            logger.error(f"Phone number parsing error: {e}")
            await update.message.reply_text("❌ Invalid phone number format. Please try again.")
            return PHONE
        
        # Store phone number and generate OTP (same as setup_command)
        # ... [rest of the phone handling code]
        
        return OTP
    
    async def verify_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify OTP code - alag-alag digits accept karein"""
        user_id = update.effective_user.id
        otp_input = update.message.text.strip()
        
        # Check if user OTP verification process mein hai
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != OTP:
            await update.message.reply_text("❌ Please start verification process with /setup")
            return ConversationHandler.END
        
        # Alag-alag digits ko combine karein (e.g., "1 2 3 4 5 6" -> "123456")
        if ' ' in otp_input:
            otp_code = ''.join(otp_input.split())
        else:
            otp_code = otp_input
        
        # Verify against expected OTP
        expected_otp = self.user_sessions[user_id].get("otp_expected")
        
        if not expected_otp or otp_code != expected_otp:
            await update.message.reply_text("❌ Invalid OTP. Please try again.")
            return OTP
        
        # Check expiration
        async with self.db.execute(
            "SELECT expires_at FROM otps WHERE user_id = ? AND otp_code = ? AND is_used = 0",
            (user_id, otp_code)
        ) as cursor:
            otp_data = await cursor.fetchone()
        
        if not otp_data:
            await update.message.reply_text("❌ Invalid OTP. Please request a new one with /setup")
            return ConversationHandler.END
        
        expires_at = otp_data[0]
        
        if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
            await update.message.reply_text("❌ OTP expired. Please request new one with /setup")
            return ConversationHandler.END
        
        # Mark OTP as used and verify user
        await self.db.execute(
            "UPDATE otps SET is_used = 1 WHERE user_id = ? AND otp_code = ?",
            (user_id, otp_code)
        )
        await self.db.execute(
            "UPDATE users SET is_verified = 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,)
        )
        await self.db.commit()
        
        # Create Telethon client for user
        client = TelegramClient(StringSession(), self.api_id, self.api_hash)
        
        try:
            await client.connect()
            await client.send_code_request(self.user_sessions[user_id]["phone"])
            await client.sign_in(self.user_sessions[user_id]["phone"], otp_code)
            
            # Save session string
            session_string = client.session.save()
            await self.db.execute(
                "UPDATE users SET session_string = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (session_string, user_id)
            )
            await self.db.commit()
            
            # Store client for later use
            self.user_clients[user_id] = client
            
            await update.message.reply_text(
                "✅ Account successfully verified!\n\n"
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
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        help_text = """
🤖 **Manual Phone Auto Forward Bot - Help** 🤖

**Available Commands:**
/setup <phone> - Verify your account with phone number
/add_forward - Set up a new forwarding rule
/list_rules - View your current forwarding rules
/stop_forward [id] - Stop a specific forwarding rule
/help - Show this help message

**How to set up forwarding:**
1. Use /setup with your phone number (e.g., /setup +919876543210)
2. OTP will be sent to your Telegram account
3. Enter OTP in the bot (you can enter digits separately: 1 2 3 4 5 6)
4. Use /add_forward to create a forwarding rule
5. Provide source channel (where to forward from)
6. Provide target channel (where to forward to)
7. Optionally add text replacement rules

**Replacement Rules Format:**
`original_text->replacement_text, another_text->another_replacement`

**Example:**
`telegram->signal, example.com->mysite.com`

Need assistance? Contact the bot administrator.
        """
        await update.message.reply_text(help_text)
    
    async def add_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new forwarding rule"""
        user_id = update.effective_user.id
        
        # Update last active time
        await self.db.execute(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,)
        )
        await self.db.commit()
        
        # Check if user is verified
        async with self.db.execute("SELECT is_verified, session_string FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or not user[0]:
            await update.message.reply_text("❌ Please verify your account first using /setup")
            return
        
        # Check if we have a valid session
        if user_id not in self.user_clients or not self.user_clients[user_id].is_connected():
            try:
                session_string = user[1]
                if not session_string:
                    await update.message.reply_text("❌ Session expired. Please verify again with /setup.")
                    return
                    
                client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                await client.connect()
                await client.get_me()
                self.user_clients[user_id] = client
            except Exception as e:
                logger.error(f"Error reconnecting user session: {e}")
                await update.message.reply_text("❌ Error accessing your account. Please verify again with /setup.")
                return
        
        # Initialize forwarding setup
        self.user_sessions[user_id] = {
            "step": FORWARD_SOURCE,
            "forwarding_rule": {}
        }
        
        await update.message.reply_text(
            "Please provide the source channel username or ID (e.g., @sourcechannel or -1001234567890):\n\n"
            "💡 Make sure you have joined this channel and have reading permissions."
        )
    
    # [Other methods: handle_forward_source, handle_forward_target, handle_forward_replacements, 
    # start_forwarding, list_rules, stop_forward, broadcast, stats, user_stats, cancel, 
    # button_handler, set_force_subscribe, check_subscription would be here]
    
    async def run(self):
        """Run the bot"""
        await self.init_db()
        
        # Load existing user sessions
        async with self.db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL AND is_verified = 1") as cursor:
            users = await cursor.fetchall()
            
            for user_id, session_string in users:
                try:
                    client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                    await client.connect()
                    await client.get_me()
                    self.user_clients[user_id] = client
                    logger.info(f"Restored session for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to restore session for user {user_id}: {e}")
        
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot is now running...")
        
        # Keep the application running
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
    
    async def shutdown(self):
        """Shutdown the bot gracefully"""
        for user_id, client in self.user_clients.items():
            if client.is_connected():
                await client.disconnect()
        
        for task in self.forwarding_tasks.values():
            task.cancel()
        
        await self.db.close()

# Main execution
if __name__ == "__main__":
    # Replace with your actual values
    BOT_TOKEN = "7738808803:AAH7M8lNwGb5UAUHA0yl8-xvy-C3yZEJ7hc"
    OWNER_ID = 123456789  # Your Telegram user ID
    API_ID = 123456  # Your Telegram API ID
    API_HASH = "your_api_hash_here"  # Your Telegram API Hash
    
    SMS_SERVICE = None
    
    bot = ManualPhoneAutoForwardBot(BOT_TOKEN, OWNER_ID, API_ID, API_HASH, SMS_SERVICE)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        asyncio.run(bot.shutdown())