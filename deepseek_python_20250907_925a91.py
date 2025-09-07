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

class CompleteAutoForwardBot:
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
        self.force_subscribe_channel = None  # Channel that users must join
        
        # Setup handlers
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup all message handlers"""
        # Conversation handler for setup process
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start), CommandHandler('setup', self.setup)],
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
        """Initialize database connection with enhanced schema"""
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
        
        await self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_verified ON users(is_verified)
        ''')
        
        await self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_rules_active ON forwarding_rules(is_active)
        ''')
        
        await self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_rules_user ON forwarding_rules(user_id)
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
            return True  # No force subscribe set
            
        # Check if user is already marked as subscribed
        async with self.db.execute(
            "SELECT has_subscribed FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result and result[0]:
                return True
                
        # Check if user has joined the channel using their Telethon client
        if user_id in self.user_clients and self.user_clients[user_id].is_connected():
            try:
                client = self.user_clients[user_id]
                entity = await client.get_entity(self.force_subscribe_channel)
                
                # Check if user is a participant in the channel
                try:
                    participant = await client(GetParticipantRequest(entity, user_id))
                    if isinstance(participant.participant, (ChannelParticipant, ChannelParticipantCreator, ChannelParticipantAdmin)):
                        # Mark user as subscribed
                        await self.db.execute(
                            "UPDATE users SET has_subscribed = 1 WHERE user_id = ?",
                            (user_id,)
                        )
                        await self.db.commit()
                        return True
                except Exception:
                    # User is not a participant
                    pass
            except Exception as e:
                logger.error(f"Error checking subscription for user {user_id}: {e}")
                
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
🤖 **Enhanced Auto Forward Bot** 🤖

I can help you automatically forward messages from any source channel to your target channel with advanced features.

**Features:**
- 🔄 Auto-forwarding from any source to your channel
- 🔧 Text and link replacement
- 🔒 Secure OTP authentication
- ⚡ Easy setup
- 📊 Message tracking and statistics

**Commands:**
/setup - Verify your account and get started
/add_forward - Add a new forwarding rule
/list_rules - List your forwarding rules
/stop_forward - Stop a forwarding rule
/help - Show this help message

To get started, use /setup to verify your account.
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
        
        # Request phone number with keyboard
        keyboard = [[KeyboardButton("📱 Share Phone Number", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "To verify your account, please share your phone number:",
            reply_markup=reply_markup
        )
        
        # Initialize user session
        self.user_sessions[user_id] = {"step": PHONE}
        
        return PHONE
    
    async def check_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user has subscribed to the required channel"""
        user_id = update.effective_user.id
        
        if not self.force_subscribe_channel:
            await update.message.reply_text("❌ No subscription channel is set up by the admin.")
            return
            
        if await self.check_user_subscription(user_id):
            await update.message.reply_text("✅ Thank you for subscribing! You can now use all bot features.")
        else:
            await update.message.reply_text(
                f"❌ You haven't joined our channel yet. Please join:\n\n"
                f"{self.force_subscribe_channel}\n\n"
                "Then use /check_subscription again to verify."
            )
    
    async def set_force_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set force subscribe channel (admin only)"""
        if not context.args:
            if self.force_subscribe_channel:
                await update.message.reply_text(
                    f"Current force subscribe channel: {self.force_subscribe_channel}\n\n"
                    "To change it, use: /set_force_subscribe @channel_username"
                )
            else:
                await update.message.reply_text(
                    "No force subscribe channel set.\n\n"
                    "To set one, use: /set_force_subscribe @channel_username"
                )
            return
            
        channel = context.args[0]
        self.force_subscribe_channel = channel
        
        # Save to database
        await self.db.execute(
            "INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('force_subscribe_channel', ?)",
            (channel,)
        )
        await self.db.commit()
        
        await update.message.reply_text(f"✅ Force subscribe channel set to: {channel}")
    
    async def handle_phone_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle phone number input (either from contact or manual input)"""
        user_id = update.effective_user.id
        
        # Check subscription
        if not await self.check_user_subscription(user_id):
            await update.message.reply_text(
                f"❌ Please join our channel first to continue:\n\n"
                f"{self.force_subscribe_channel}\n\n"
                "After joining, use /check_subscription to verify."
            )
            return ConversationHandler.END
            
        if user_id not in self.user_sessions or self.user_sessions[user_id].get("step") != PHONE:
            await update.message.reply_text("Please start the verification process with /setup")
            return ConversationHandler.END
        
        # Check if message contains contact
        if update.message.contact:
            phone_number = update.message.contact.phone_number
        else:
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
        
        # Check if this phone number is already registered with another account
        async with self.db.execute("SELECT user_id FROM users WHERE phone = ? AND user_id != ?", 
                                  (formatted_number, user_id)) as cursor:
            existing_user = await cursor.fetchone()
            
        if existing_user:
            await update.message.reply_text(
                "❌ This phone number is already registered with another account. "
                "Please use a different phone number or contact support."
            )
            return PHONE
        
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
        
        # Send OTP via SMS (if service available) or via message
        if self.sms_service:
            try:
                await self.sms_service.send_sms(formatted_number, f"Your verification code is: {otp}")
                await update.message.reply_text(
                    f"✅ OTP sent to {formatted_number}. Please enter the code within 10 minutes.",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception as e:
                logger.error(f"SMS sending failed: {e}")
                await update.message.reply_text(
                    f"❌ Failed to send SMS. Your OTP is: {otp}. Please enter this code.",
                    reply_markup=ReplyKeyboardRemove()
                )
        else:
            await update.message.reply_text(
                f"📋 Your OTP is: {otp}. Please enter this code within 10 minutes.",
                reply_markup=ReplyKeyboardRemove()
            )
        
        # Update user session
        self.user_sessions[user_id] = {
            "step": OTP,
            "phone": formatted_number
        }
        
        return OTP
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        help_text = """
🤖 **Enhanced Auto Forward Bot - Help** 🤖

**Available Commands:**
/setup - Verify your account with OTP
/add_forward - Set up a new forwarding rule
/list_rules - View your current forwarding rules
/stop_forward [id] - Stop a specific forwarding rule
/help - Show this help message
/check_subscription - Check if you've joined the required channel

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

Need assistance? Contact the bot administrator.
        """
        await update.message.reply_text(help_text)
    
    async def setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start setup process directly"""
        return await self.start(update, context)
    
    async def verify_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify OTP code and create user session"""
        user_id = update.effective_user.id
        
        # Check subscription
        if not await self.check_user_subscription(user_id):
            await update.message.reply_text(
                f"❌ Please join our channel first to continue:\n\n"
                f"{self.force_subscribe_channel}\n\n"
                "After joining, use /check_subscription to verify."
            )
            return ConversationHandler.END
            
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
                "UPDATE users SET is_verified = 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
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
                    "UPDATE users SET session_string = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
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
        
        # Check subscription
        if not await self.check_user_subscription(user_id):
            await update.message.reply_text(
                f"❌ Please join our channel first to continue:\n\n"
                f"{self.force_subscribe_channel}\n\n"
                "After joining, use /check_subscription to verify."
            )
            return
        
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
        
        # Check if user has reached maximum forwarding rules (prevent abuse)
        async with self.db.execute(
            "SELECT COUNT(*) FROM forwarding_rules WHERE user_id = ? AND is_active = 1", 
            (user_id,)
        ) as cursor:
            rule_count = (await cursor.fetchone())[0]
            
        if rule_count >= 10:  # Limit to 10 active rules per user
            await update.message.reply_text(
                "❌ You have reached the maximum number of active forwarding rules (10). "
                "Please stop some rules with /stop_forward before adding new ones."
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
    
    # [Rest of the methods remain the same as previous version...]
    # handle_forward_source, handle_forward_target, handle_forward_replacements,
    # start_forwarding, list_rules, stop_forward, broadcast, stats, user_stats,
    # cancel, button_handler methods would be here
    
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
                    
                    # Test the connection
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
            # Create a future that will never complete to keep the bot running
            await asyncio.Future()
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
        
        # Close database connection
        await self.db.close()

# Main execution
if __name__ == "__main__":
    # Replace with your actual values
    BOT_TOKEN = "7738808803:AAH7M8lNwGb5UAUHA0yl8-xvy-C3yZEJ7hc"  # From BotFather
    OWNER_ID = 123456789  # Your Telegram user ID
    API_ID = 123456  # Your Telegram API ID from https://my.termux.org
    API_HASH = "your_api_hash_here"  # Your Telegram API Hash
    
    # Optional: Configure SMS service for OTP delivery
    # SMS_SERVICE = SomeSmsService(api_key="your_api_key")
    SMS_SERVICE = None  # Set to None to send OTP via Telegram message
    
    bot = CompleteAutoForwardBot(BOT_TOKEN, OWNER_ID, API_ID, API_HASH, SMS_SERVICE)
    
    try:
        # Run the bot
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        # Cleanup
        asyncio.run(bot.shutdown())