import os
import requests
import telebot
import json
import logging
import time
import threading
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import re
from admin import AdminManager

# 🎨 Configure logging with style
logging.basicConfig(
    level=logging.INFO,
    format='🎯 %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 🔑 Bot Token (Replace with your actual token)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# 🚀 Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# 👑 Initialize Admin Manager
admin_manager = AdminManager(bot)

# 💾 Store user sessions
user_sessions = {}

class TeraboxDownloader:
    # ... (Keep your existing TeraboxDownloader class exactly as is) ...
    def __init__(self):
        self.apis = [
            self.api_terabox_dl,
            self.api_tb_botbns,
            self.api_terabox_online,
            self.api_terabox_api
        ]
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.terabox.com/'
        })

def api_terabox_dl(self, link):
        """🎯 API 1: terabox-dl.com"""
        try:
            url = "https://terabox-dl.com/api/get-info"
            payload = {'url': link}
            response = self.session.post(url, data=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API1 Success: {data.get('filename', 'Unknown')}")
                return self.format_response(data)
            return None
        except Exception as e:
            logger.error(f"❌ API1 Error: {e}")
            return None

    def api_tb_botbns(self, link):
        """🎯 API 2: tb.botbns.xyz"""
        try:
            url = "https://tb.botbns.xyz/api/getInfo"
            payload = {'url': link}
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    file_data = data.get('data', {})
                    logger.info(f"✅ API2 Success: {file_data.get('filename', 'Unknown')}")
                    return self.format_response(file_data)
            return None
        except Exception as e:
            logger.error(f"❌ API2 Error: {e}")
            return None

    def api_terabox_online(self, link):
        """🎯 API 3: Online API"""
        try:
            url = "https://terabox-downloader.onrender.com/api"
            payload = {'url': link}
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API3 Success: {data.get('filename', 'Unknown')}")
                return self.format_response(data)
            return None
        except Exception as e:
            logger.error(f"❌ API3 Error: {e}")
            return None

    def api_terabox_api(self, link):
        """🎯 API 4: Alternative API"""
        try:
            url = "https://terabox-api.vercel.app/api"
            payload = {'url': link}
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API4 Success: {data.get('filename', 'Unknown')}")
                return self.format_response(data)
            return None
        except Exception as e:
            logger.error(f"❌ API4 Error: {e}")
            return None

    def format_response(self, data):
        """✨ Format API response consistently"""
        if not data:
            return None

        result = {
            'filename': data.get('filename', '📄 Unknown File'),
            'size': data.get('size', '📦 Unknown Size'),
            'duration': data.get('duration', '⏱️ N/A'),
            'download_url': data.get('download_url', ''),
            'qualities': {}
        }

        # Handle different quality formats
        if data.get('qualities'):
            result['qualities'] = data['qualities']
        elif data.get('download_links'):
            result['qualities'] = {'🚀 Direct': data['download_links']}
        elif data.get('url'):
            result['download_url'] = data['url']

        return result

    def get_download_info(self, link):
        """🔄 Try all APIs with proper error handling"""
        logger.info(f"🔗 Processing link: {link}")
        
        for i, api_method in enumerate(self.apis):
            try:
                logger.info(f"🔄 Trying API {i+1}...")
                result = api_method(link)
                if result and (result.get('download_url') or result.get('qualities')):
                    logger.info(f"✅ API {i+1} successful!")
                    return result
                time.sleep(1)
            except Exception as e:
                logger.error(f"❌ API {i+1} failed: {e}")
                continue
        
        return None

# 🚀 Initialize downloader
downloader = TeraboxDownloader()

def is_terabox_link(text):
    """🔍 Check if text is a valid Terabox link"""
    patterns = [
        r'https?://(www\.)?terabox\.com/[^\s]+',
        r'https?://(www\.)?1024terabox\.com/[^\s]+',
        r'https?://(www\.)?teraboxapp\.com/[^\s]+'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False

def format_file_size(size_str):
    """📊 Format file size for better display"""
    if not size_str or size_str == '📦 Unknown Size':
        return '📦 Unknown Size'
    
    try:
        size_num = float(re.findall(r'\d+\.?\d*', size_str)[0])
        
        for unit in ['Bytes', 'KB', 'MB', 'GB']:
            if size_num < 1024.0:
                return f"💾 {size_num:.2f} {unit}"
            size_num /= 1024.0
        return f"💾 {size_num:.2f} TB"
    except:
        return '📦 Unknown Size'

def update_user_stats(user_id, username, first_name, last_name, download_count=0):
    """Update user statistics in database"""
    try:
        import sqlite3
        conn = sqlite3.connect(admin_manager.db_path)
        cursor = conn.cursor()
        
        if download_count > 0:
            cursor.execute('''
                UPDATE users 
                SET downloads_count = downloads_count + ?, last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (download_count, user_id))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error updating user stats: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """🎉 Send welcome message with force sub check"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Update user stats
    update_user_stats(user_id, username, first_name, None)
    
    # Check force subscription
    is_subscribed, not_joined_channels = admin_manager.check_user_subscription(user_id)
    
    if not is_subscribed:
        # Show force subscription message
        channels_text = "\n".join([f"• {channel}" for channel in not_joined_channels])
        
        force_sub_text = f"""
🔒 <b>SUBSCRIPTION REQUIRED</b>

To use this bot, you need to join our channel(s) first:

{channels_text}

⚠️ Please join the channel(s) above and then press the verification button below.
        """
        
        keyboard = InlineKeyboardMarkup()
        for channel in not_joined_channels:
            keyboard.add(InlineKeyboardButton(
                f"📢 Join {channel}",
                url=f"https://t.me/{channel[1:]}"
            ))
        
        keyboard.add(InlineKeyboardButton(
            "✅ I've Joined - Verify",
            callback_data="check_subscription"
        ))
        
        bot.send_message(message.chat.id, force_sub_text, reply_markup=keyboard)
        return
    
    # User is subscribed, show welcome message
    welcome_text, welcome_image = admin_manager.get_welcome_message(
        first_name or "User", 
        f"@{username}" if username else "User"
    )
    
    if welcome_image:
        bot.send_photo(
            message.chat.id,
            welcome_image,
            caption=welcome_text,
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
                '📖 How to Use', 
                '🔧 Support',
                '📊 Statistics',
                '🔄 New Download'
            )
        )
    else:
        welcome_text += """

📋 <b>HOW TO USE:</b>
1. 🔗 Send any TeraBox link
2. ⏳ Wait for processing
3. 📥 Download your files!

⚡ <b>COMMANDS:</b>
/start - Start the bot
/help - Show help
/stats - Your statistics
        """
        
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
                '📖 How to Use', 
                '🔧 Support',
                '📊 Statistics',
                '🔄 New Download'
            )
        )

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def handle_subscription_check(call):
    """Handle subscription verification"""
    user_id = call.from_user.id
    is_subscribed, not_joined_channels = admin_manager.check_user_subscription(user_id)
    
    if is_subscribed:
        # User has joined all channels
        first_name = call.from_user.first_name
        username = call.from_user.username
        
        welcome_text, welcome_image = admin_manager.get_welcome_message(
            first_name or "User", 
            f"@{username}" if username else "User"
        )
        
        if welcome_image:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_photo(
                call.message.chat.id,
                welcome_image,
                caption=welcome_text,
                reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
                    '📖 How to Use', 
                    '🔧 Support',
                    '📊 Statistics',
                    '🔄 New Download'
                )
            )
        else:
            bot.edit_message_text(
                f"✅ <b>Verification Successful!</b>\n\n{welcome_text}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
    else:
        # User still hasn't joined
        bot.answer_callback_query(
            call.id,
            "❌ You haven't joined all required channels yet!",
            show_alert=True
        )

@bot.message_handler(commands=['admin', 'broadcast', 'stats', 'addadmin', 'removeadmin', 'forceadd', 'forceremove', 'setwelcome', 'users'])
def handle_admin_commands(message):
    """Handle admin commands"""
    admin_manager.handle_admin_command(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callbacks(call):
    """Handle admin callback queries"""
    admin_manager.handle_admin_callback(call)

@bot.message_handler(func=lambda message: message.text in ['📖 How to Use', '🔧 Support', '📊 Statistics', '🔄 New Download'])
def handle_buttons(message):
    """Handle button clicks"""
    # ... (Keep your existing button handler code) ...

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """🎯 Handle all incoming messages"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check force subscription for non-start messages
    is_subscribed, not_joined_channels = admin_manager.check_user_subscription(user_id)
    if not is_subscribed and not text.startswith('/'):
        bot.reply_to(message, 
            "❌ <b>Subscription Required!</b>\n\n"
            "Please join our channel(s) first using /start command."
        )
        return
    
    # Update user activity
    update_user_stats(
        user_id, 
        message.from_user.username, 
        message.from_user.first_name, 
        message.from_user.last_name
    )
    
    # Handle Terabox links
    if is_terabox_link(text):
        # ... (Keep your existing Terabox link handling code) ...
        processing_msg = bot.reply_to(message, 
            "⏳ <b>Processing Your Link...</b>",
            disable_web_page_preview=True
        )
        
        try:
            file_info = downloader.get_download_info(text)
            if file_info:
                # Update download count
                update_user_stats(user_id, None, None, None, 1)
                
                # ... (Rest of your download handling code) ...
            else:
                bot.edit_message_text(
                    "❌ Download Failed!",
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id
                )
        except Exception as e:
            logger.error(f"Error: {e}")
            bot.edit_message_text(
                "❌ Error occurred!",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id
            )
    elif not text.startswith('/'):
        bot.reply_to(message, 
            "❌ <b>Invalid Terabox Link!</b>\n\n"
            "Please send a valid Terabox link.",
            disable_web_page_preview=True
        )

def main():
    """🚀 Main function to start the bot"""
    logger.info("🎯 Starting Enhanced Terabox Downloader Bot...")
    
    try:
        bot_info = bot.get_me()
        logger.info(f"✅ Bot started successfully: @{bot_info.username}")
        logger.info(f"👑 Admin system initialized with {len(admin_manager.admin_ids)} admins")
        
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
        
    except Exception as e:
        logger.error(f"💥 Bot failed to start: {e}")
        logger.info("🔄 Restarting bot in 10 seconds...")
        time.sleep(10)
        main()

if __name__ == "__main__":
    print("""
    🚀 ENHANCED TERABOX DOWNLOADER BOT
    👑 Advanced Admin System
    📊 User Management
    📢 Broadcast System
    🔥 Ready to Serve!
    """)
    
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
            logger.info("🔄 Restarting in 15 seconds...")
            time.sleep(15)
