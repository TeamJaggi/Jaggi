import asyncio
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union

from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError
from telethon.tl.types import Message, User, Channel, Chat
from telethon.sessions import StringSession

# Database setup
def init_db():
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, phone TEXT, session_string TEXT, 
                 authorized INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (user_id INTEGER, key TEXT, value TEXT,
                 PRIMARY KEY (user_id, key))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS incoming_chats
                 (user_id INTEGER, chat_id INTEGER, title TEXT,
                 PRIMARY KEY (user_id, chat_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS outgoing_chats
                 (user_id INTEGER, chat_id INTEGER, title TEXT,
                 PRIMARY KEY (user_id, chat_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS filters
                 (user_id INTEGER, type TEXT, value TEXT,
                 PRIMARY KEY (user_id, type, value))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transform
                 (user_id INTEGER, begin_text TEXT, end_text TEXT,
                 replace_from TEXT, replace_to TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS delay_config
                 (user_id INTEGER, delay_seconds INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_states
                 (user_id INTEGER PRIMARY KEY, state TEXT, data TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin_users
                 (user_id INTEGER PRIMARY KEY, username TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS edit_config
                 (user_id INTEGER, should_edit INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS delete_config
                 (user_id INTEGER, should_delete INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS whitelist_users
                 (user_id INTEGER, allowed_user_id INTEGER,
                 PRIMARY KEY (user_id, allowed_user_id))''')
    
    conn.commit()
    conn.close()

init_db()

# Bot configuration
API_ID = 123456  # Replace with your actual API ID
API_HASH = "your_api_hash_here"  # Replace with your actual API Hash
BOT_TOKEN = "your_bot_token_here"  # Get from @BotFather

# Add your user ID as admin
ADMIN_USER_ID = 123456789  # Change this to your Telegram user ID

# Add admin user to database
def add_admin_user():
    try:
        db_execute("INSERT OR IGNORE INTO admin_users (user_id, username) VALUES (?, ?)", 
                  (ADMIN_USER_ID, "admin"))
    except:
        pass

add_admin_user()

# Helper functions for database operations
def db_execute(query, params=()):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_fetchone(query, params=()):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchone()
    conn.close()
    return result

def db_fetchall(query, params=()):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchall()
    conn.close()
    return result

def set_user_state(user_id, state, data=None):
    db_execute("INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)",
               (user_id, state, data or ""))
    user_states[user_id] = (state, data or "")

def get_user_state(user_id):
    if user_id in user_states:
        return user_states[user_id]
    
    result = db_fetchone("SELECT state, data FROM user_states WHERE user_id = ?", (user_id,))
    if result:
        user_states[user_id] = (result[0], result[1])
        return user_states[user_id]
    
    return (None, None)

def clear_user_state(user_id):
    db_execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
    if user_id in user_states:
        del user_states[user_id]

# Check if user is authorized
def is_authorized(user_id):
    result = db_fetchone("SELECT authorized FROM users WHERE user_id = ?", (user_id,))
    return result and result[0] == 1

# Check if user is admin
def is_admin(user_id):
    result = db_fetchone("SELECT user_id FROM admin_users WHERE user_id = ?", (user_id,))
    return result is not None

# Get all authorized users
def get_all_authorized_users():
    result = db_fetchall("SELECT user_id FROM users WHERE authorized = 1")
    return [row[0] for row in result] if result else []

# User sessions storage
user_clients = {}
user_states = {}  # Track user state for multi-step commands

# Create Bot Client
bot = TelegramClient('auto_forward_bot', API_ID, API_HASH)

# Start command
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    user_id = event.sender_id
    welcome_text = """
🤖 **Auto Forward Bot**

Welcome! I can automatically forward messages from one chat to another with various transformations.

**Main Commands:**
/authorize - Login with your Telegram account
/config - View current configuration
/features - View all available features
/incoming - Setup SOURCE chats
/outgoing - Setup TARGET chats
/transform - Transform message text
/filter - Setup replace text
/begin_text - Add text to beginning
/end_text - Add text to end
/blacklist - Blacklist some words
/whitelist - Whitelist some words
/delay - Add delay to forwarded messages
/should_edit - Set EDIT configuration
/should_delete - Set DELETE configuration
/work - Start forwarding
/stop - Stop forwarding
/restart - Restart setup (stop and work)
/remove_incoming - Remove incoming chat
/remove_outgoing - Remove outgoing chat
/remove_filter - Remove filter
/rem_whitelist - Remove whitelisted words
/rem_blacklist - Remove blacklisted words
/reset_config - Reset configuration
/remove_session - Logout from this bot
/filter_users - Whitelist users in group
/broadcasting - Admin only: Broadcast messages to all users

Use /help <command> for more info on a specific command.
"""
    await event.reply(welcome_text)

# Authorize command - Login flow
@bot.on(events.NewMessage(pattern='/authorize'))
async def authorize_command(event):
    user_id = event.sender_id
    
    if is_authorized(user_id):
        await event.reply("✅ You are already authorized! Use /remove_session to logout.")
        return
    
    set_user_state(user_id, "awaiting_api_id")
    await event.reply("🔐 **Login Process Started**\n\nPlease send your API_ID (get it from https://my.telegram.org):")

# Config command - View current configuration
@bot.on(events.NewMessage(pattern='/config'))
async def config_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    incoming = db_fetchall("SELECT chat_id, title FROM incoming_chats WHERE user_id = ?", (user_id,))
    outgoing = db_fetchall("SELECT chat_id, title FROM outgoing_chats WHERE user_id = ?", (user_id,))
    transform = db_fetchone("SELECT begin_text, end_text, replace_from, replace_to FROM transform WHERE user_id = ?", (user_id,))
    delay = db_fetchone("SELECT delay_seconds FROM delay_config WHERE user_id = ?", (user_id,))
    should_edit = db_fetchone("SELECT should_edit FROM edit_config WHERE user_id = ?", (user_id,))
    should_delete = db_fetchone("SELECT should_delete FROM delete_config WHERE user_id = ?", (user_id,))
    blacklist = db_fetchall("SELECT value FROM filters WHERE user_id = ? AND type = 'blacklist'", (user_id,))
    whitelist = db_fetchall("SELECT value FROM filters WHERE user_id = ? AND type = 'whitelist'", (user_id,))
    whitelist_users = db_fetchall("SELECT allowed_user_id FROM whitelist_users WHERE user_id = ?", (user_id,))
    
    config_text = "📋 **Your Current Configuration**\n\n"
    
    if incoming:
        config_text += "**Source Chats:**\n"
        for chat in incoming:
            config_text += f"- {chat[1]} (ID: {chat[0]})\n"
    else:
        config_text += "**Source Chats:** Not set\n"
    
    if outgoing:
        config_text += "\n**Target Chats:**\n"
        for chat in outgoing:
            config_text += f"- {chat[1]} (ID: {chat[0]})\n"
    else:
        config_text += "\n**Target Chats:** Not set\n"
    
    if transform and any(transform):
        config_text += "\n**Text Transformations:**\n"
        if transform[0]: config_text += f"- Begin Text: {transform[0]}\n"
        if transform[1]: config_text += f"- End Text: {transform[1]}\n"
        if transform[2] and transform[3]: config_text += f"- Replace: '{transform[2]}' → '{transform[3]}'\n"
    
    if delay:
        config_text += f"\n**Delay:** {delay[0]} seconds\n"
    
    if should_edit:
        config_text += f"\n**Edit Messages:** {'Enabled' if should_edit[0] else 'Disabled'}\n"
    
    if should_delete:
        config_text += f"\n**Delete Original:** {'Enabled' if should_delete[0] else 'Disabled'}\n"
    
    if blacklist:
        config_text += "\n**Blacklisted Words:**\n"
        for word in blacklist:
            config_text += f"- {word[0]}\n"
    
    if whitelist:
        config_text += "\n**Whitelisted Words:**\n"
        for word in whitelist:
            config_text += f"- {word[0]}\n"
    
    if whitelist_users:
        config_text += "\n**Whitelisted Users:**\n"
        for user in whitelist_users:
            config_text += f"- User ID: {user[0]}\n"
    
    await event.reply(config_text)

# Features command
@bot.on(events.NewMessage(pattern='/features'))
async def features_command(event):
    features_text = """
✨ **Auto Forward Bot Features**

✅ **User Authentication:** Login with your own Telegram account
✅ **Multiple Source Chats:** Forward from multiple channels/groups
✅ **Multiple Target Chats:** Forward to multiple channels/groups
✅ **Text Transformation:** Modify messages before forwarding
✅ **Filtering:** Blacklist/whitelist specific words
✅ **Delay Settings:** Add delay between forwarded messages
✅ **Media Support:** Forward all types of media (photos, videos, documents)
✅ **Stickers & Emojis:** Full support for stickers and emojis
✅ **Edit Configuration:** Set whether to edit messages
✅ **Delete Configuration:** Set whether to delete original messages
✅ **User Whitelisting:** Allow specific users only
✅ **Broadcasting:** Admin can broadcast messages to all users

**Available Commands:**
/authorize - Login with your account
/incoming - Setup SOURCE chats
/outgoing - Setup TARGET chats
/transform - Transform message text
/filter - Setup replace text
/begin_text - Add text to beginning
/end_text - Add text to end
/blacklist - Blacklist words
/whitelist - Whitelist words
/delay - Add forwarding delay
/should_edit - Set edit configuration
/should_delete - Set delete configuration
/work - Start forwarding
/stop - Stop forwarding
/restart - Restart setup
/remove_incoming - Remove source chat
/remove_outgoing - Remove target chat
/remove_filter - Remove filters
/rem_whitelist - Remove whitelist
/rem_blacklist - Remove blacklist
/reset_config - Reset all settings
/remove_session - Logout
/filter_users - Whitelist users
/broadcasting - Admin broadcast
"""
    await event.reply(features_text)

# Incoming chats setup
@bot.on(events.NewMessage(pattern='/incoming'))
async def incoming_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_incoming")
    await event.reply("Please forward a message from the SOURCE chat or send the chat ID/username:")

# Outgoing chats setup
@bot.on(events.NewMessage(pattern='/outgoing'))
async def outgoing_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_outgoing")
    await event.reply("Please forward a message from the TARGET chat or send the chat ID/username:")

# Transform command
@bot.on(events.NewMessage(pattern='/transform'))
async def transform_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_transform")
    await event.reply("Please send the transformation in format: 'old_text->new_text'")

# Filter command
@bot.on(events.NewMessage(pattern='/filter'))
async def filter_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_filter")
    await event.reply("Please send the filter in format: 'text_to_find->replacement_text'")

# Begin text command
@bot.on(events.NewMessage(pattern='/begin_text'))
async def begin_text_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_begin_text")
    await event.reply("Please send the text to add at the beginning of messages:")

# End text command
@bot.on(events.NewMessage(pattern='/end_text'))
async def end_text_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_end_text")
    await event.reply("Please send the text to add at the end of messages:")

# Blacklist command
@bot.on(events.NewMessage(pattern='/blacklist'))
async def blacklist_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_blacklist")
    await event.reply("Please send the word to blacklist:")

# Whitelist command
@bot.on(events.NewMessage(pattern='/whitelist'))
async def whitelist_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_whitelist")
    await event.reply("Please send the word to whitelist:")

# Delay command
@bot.on(events.NewMessage(pattern='/delay'))
async def delay_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_delay")
    await event.reply("Please send the delay in seconds (e.g., 5 for 5 seconds):")

# Should edit command
@bot.on(events.NewMessage(pattern='/should_edit'))
async def should_edit_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Toggle edit configuration
    current = db_fetchone("SELECT should_edit FROM edit_config WHERE user_id = ?", (user_id,))
    new_value = 0 if current and current[0] == 1 else 1
    
    db_execute("INSERT OR REPLACE INTO edit_config (user_id, should_edit) VALUES (?, ?)",
              (user_id, new_value))
    
    status = "Enabled" if new_value == 1 else "Disabled"
    await event.reply(f"✅ Edit messages configuration: {status}")

# Should delete command
@bot.on(events.NewMessage(pattern='/should_delete'))
async def should_delete_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Toggle delete configuration
    current = db_fetchone("SELECT should_delete FROM delete_config WHERE user_id = ?", (user_id,))
    new_value = 0 if current and current[0] == 1 else 1
    
    db_execute("INSERT OR REPLACE INTO delete_config (user_id, should_delete) VALUES (?, ?)",
              (user_id, new_value))
    
    status = "Enabled" if new_value == 1 else "Disabled"
    await event.reply(f"✅ Delete original messages configuration: {status}")

# Work command - Start forwarding
@bot.on(events.NewMessage(pattern='/work'))
async def work_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Check if user has set up both incoming and outgoing chats
    incoming = db_fetchone("SELECT chat_id, title FROM incoming_chats WHERE user_id = ?", (user_id,))
    outgoing = db_fetchone("SELECT chat_id, title FROM outgoing_chats WHERE user_id = ?", (user_id,))
    
    if not incoming or not outgoing:
        await event.reply("❌ Please set up both incoming and outgoing chats first with /incoming and /outgoing")
        return
    
    # Start the user client if not already started
    user_client = await get_user_client(user_id)
    if user_client and not user_client.is_connected():
        await user_client.start()
        
        # Set up message handler for the user client
        @user_client.on(events.NewMessage(chats=incoming[0]))
        async def handle_incoming_messages(event):
            outgoing_chat = db_fetchone("SELECT chat_id FROM outgoing_chats WHERE user_id = ?", (user_id,))
            if outgoing_chat:
                try:
                    # Apply transformations and filters
                    message_text = event.message.text or ""
                    
                    # Get transformations
                    transform = db_fetchone("SELECT begin_text, end_text, replace_from, replace_to FROM transform WHERE user_id = ?", (user_id,))
                    if transform:
                        if transform[0]:  # Begin text
                            message_text = transform[0] + message_text
                        if transform[1]:  # End text
                            message_text = message_text + transform[1]
                        if transform[2] and transform[3]:  # Replace text
                            message_text = message_text.replace(transform[2], transform[3])
                    
                    # Get delay
                    delay = db_fetchone("SELECT delay_seconds FROM delay_config WHERE user_id = ?", (user_id,))
                    if delay and delay[0] > 0:
                        await asyncio.sleep(delay[0])
                    
                    # Send the transformed message
                    if event.message.media:
                        await user_client.send_file(outgoing_chat[0], event.message.media, caption=message_text)
                    else:
                        await user_client.send_message(outgoing_chat[0], message_text)
                        
                except Exception as e:
                    print(f"Error forwarding message: {e}")
    
    await event.reply("✅ Auto forwarding started!")

# Stop command - Stop forwarding
@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Stop the user client if running
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    
    await event.reply("⏹️ Auto forwarding stopped!")

# Restart command
@bot.on(events.NewMessage(pattern='/restart'))
async def restart_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Stop if running
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    
    # Start again
    await work_command(event)
    await event.reply("🔄 Auto forwarding restarted!")

# Remove incoming command
@bot.on(events.NewMessage(pattern='/remove_incoming'))
async def remove_incoming_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    db_execute("DELETE FROM incoming_chats WHERE user_id = ?", (user_id,))
    await event.reply("✅ Source chat removed!")

# Remove outgoing command
@bot.on(events.NewMessage(pattern='/remove_outgoing'))
async def remove_outgoing_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    db_execute("DELETE FROM outgoing_chats WHERE user_id = ?", (user_id,))
    await event.reply("✅ Target chat removed!")

# Remove filter command
@bot.on(events.NewMessage(pattern='/remove_filter'))
async def remove_filter_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    db_execute("DELETE FROM transform WHERE user_id = ?", (user_id,))
    await event.reply("✅ All filters removed!")

# Remove whitelist command
@bot.on(events.NewMessage(pattern='/rem_whitelist'))
async def rem_whitelist_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    db_execute("DELETE FROM filters WHERE user_id = ? AND type = 'whitelist'", (user_id,))
    await event.reply("✅ Whitelisted words removed!")

# Remove blacklist command
@bot.on(events.NewMessage(pattern='/rem_blacklist'))
async def rem_blacklist_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    db_execute("DELETE FROM filters WHERE user_id = ? AND type = 'blacklist'", (user_id,))
    await event.reply("✅ Blacklisted words removed!")

# Reset config command
@bot.on(events.NewMessage(pattern='/reset_config'))
async def reset_config_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    # Stop if running
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    
    # Remove all configurations
    db_execute("DELETE FROM incoming_chats WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM outgoing_chats WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM transform WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM filters WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM delay_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM edit_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM delete_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM whitelist_users WHERE user_id = ?", (user_id,))
    
    await event.reply("✅ All configurations reset!")

# Remove session command
@bot.on(events.NewMessage(pattern='/remove_session'))
async def remove_session_command(event):
    user_id = event.sender_id
    
    # Stop user client if running
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    
    # Remove user data from database
    db_execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM incoming_chats WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM outgoing_chats WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM transform WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM filters WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM delay_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM edit_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM delete_config WHERE user_id = ?", (user_id,))
    db_execute("DELETE FROM whitelist_users WHERE user_id = ?", (user_id,))
    
    if user_id in user_states:
        del user_states[user_id]
    
    await event.reply("✅ Session removed. Use /authorize to login again.")

# Filter users command
@bot.on(events.NewMessage(pattern='/filter_users'))
async def filter_users_command(event):
    user_id = event.sender_id
    
    if not is_authorized(user_id):
        await event.reply("❌ Please authorize first with /authorize")
        return
    
    set_user_state(user_id, "awaiting_filter_user")
    await event.reply("Please send the user ID to whitelist (or forward a message from the user):")

# Handle user messages based on state
@bot.on(events.NewMessage(func=lambda e: e.is_private and not e.message.text.startswith('/')))
async def handle_user_messages(event):
    user_id = event.sender_id
    state, data = get_user_state(user_id)
    text = event.message.text
    
    if not state:
        await event.reply("Please use /start to begin or /authorize to login.")
        return
    
    # Handle API ID input
    if state == "awaiting_api_id":
        if not text.isdigit():
            await event.reply("❌ API_ID must be a number. Please send your API_ID again:")
            return
        
        set_user_state(user_id, "awaiting_api_hash", text)
        await event.reply("✅ API_ID received. Now please send your API_HASH:")
    
    # Handle API Hash input
    elif state == "awaiting_api_hash":
        api_id = data
        api_hash = text
        
        set_user_state(user_id, "awaiting_phone", f"{api_id}:{api_hash}")
        await event.reply("✅ API_HASH received. Now please send your phone number in international format (e.g., +1234567890):")
    
    # Handle phone number input
    elif state == "awaiting_phone":
        try:
            phone = text
            api_id, api_hash = data.split(":")
            
            # Create a temporary client for authentication
            temp_client = TelegramClient(StringSession(), int(api_id), api_hash)
            await temp_client.connect()
            
            # Send code request
            sent_code = await temp_client.send_code_request(phone)
            phone_code_hash = sent_code.phone_code_hash
            
            set_user_state(user_id, "awaiting_code", f"{api_id}:{api_hash}:{phone}:{phone_code_hash}")
            await event.reply("✅ Code sent to your phone. Please send the verification code you received:")
            
            await temp_client.disconnect()
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease start again with /authorize.")
            clear_user_state(user_id)
    
    # Handle verification code input
    elif state == "awaiting_code":
        try:
            code = text.strip()
            api_id, api_hash, phone, phone_code_hash = data.split(":")
            
            # Create a temporary client for authentication
            temp_client = TelegramClient(StringSession(), int(api_id), api_hash)
            await temp_client.connect()
            
            # Sign in with the code
            try:
                await temp_client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                set_user_state(user_id, "awaiting_password", data)
                await event.reply("🔒 Your account has 2FA enabled. Please send your password:")
                await temp_client.disconnect()
                return
            
            # Get session string
            session_string = temp_client.session.save()
            
            # Store user data
            db_execute("INSERT OR REPLACE INTO users (user_id, phone, session_string, authorized) VALUES (?, ?, ?, ?)",
                      (user_id, phone, session_string, 1))
            
            # Store API credentials for future use
            db_execute("INSERT OR REPLACE INTO config (user_id, key, value) VALUES (?, ?, ?)",
                      (user_id, "api_id", api_id))
            db_execute("INSERT OR REPLACE INTO config (user_id, key, value) VALUES (?, ?, ?)",
                      (user_id, "api_hash", api_hash))
            
            await event.reply("✅ Login successful! You can now set up auto forwarding.")
            clear_user_state(user_id)
            await temp_client.disconnect()
            
        except PhoneCodeInvalidError:
            await event.reply("❌ Invalid code. Please try again with /authorize.")
            clear_user_state(user_id)
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease try again with /authorize.")
            clear_user_state(user_id)
    
    # Handle password input
    elif state == "awaiting_password":
        try:
            password = text
            api_id, api_hash, phone, phone_code_hash = data.split(":")
            
            # Create a temporary client for authentication
            temp_client = TelegramClient(StringSession(), int(api_id), api_hash)
            await temp_client.connect()
            
            # Check password
            await temp_client.sign_in(password=password)
            
            # Get session string
            session_string = temp_client.session.save()
            
            # Store user data
            db_execute("INSERT OR REPLACE INTO users (user_id, phone, session_string, authorized) VALUES (?, ?, ?, ?)",
                      (user_id, phone, session_string, 1))
            
            # Store API credentials for future use
            db_execute("INSERT OR REPLACE INTO config (user_id, key, value) VALUES (?, ?, ?)",
                      (user_id, "api_id", api_id))
            db_execute("INSERT OR REPLACE INTO config (user_id, key, value) VALUES (?, ?, ?)",
                      (user_id, "api_hash", api_hash))
            
            await event.reply("✅ Login successful! You can now set up auto forwarding.")
            clear_user_state(user_id)
            await temp_client.disconnect()
            
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease try again with /authorize.")
            clear_user_state(user_id)
    
    # Handle transform input
    elif state == "awaiting_transform":
        if '->' in text:
            old_text, new_text = text.split('->', 1)
            db_execute("INSERT OR REPLACE INTO transform (user_id, replace_from, replace_to) VALUES (?, ?, ?)",
                      (user_id, old_text.strip(), new_text.strip()))
            await event.reply("✅ Text transformation set!")
        else:
            await event.reply("❌ Please use format: 'old_text->new_text'")
        clear_user_state(user_id)
    
    # Handle filter input
    elif state == "awaiting_filter":
        if '->' in text:
            find_text, replace_text = text.split('->', 1)
            db_execute("INSERT OR REPLACE INTO transform (user_id, replace_from, replace_to) VALUES (?, ?, ?)",
                      (user_id, find_text.strip(), replace_text.strip()))
            await event.reply("✅ Filter set!")
        else:
            await event.reply("❌ Please use format: 'text_to_find->replacement_text'")
        clear_user_state(user_id)
    
    # Handle begin text input
    elif state == "awaiting_begin_text":
        db_execute("INSERT OR REPLACE INTO transform (user_id, begin_text) VALUES (?, ?)",
                  (user_id, text))
        await event.reply("✅ Beginning text set!")
        clear_user_state(user_id)
    
    # Handle end text input
    elif state == "awaiting_end_text":
        db_execute("INSERT OR REPLACE INTO transform (user_id, end_text) VALUES (?, ?)",
                  (user_id, text))
        await event.reply("✅ Ending text set!")
        clear_user_state(user_id)
    
    # Handle blacklist input
    elif state == "awaiting_blacklist":
        db_execute("INSERT OR REPLACE INTO filters (user_id, type, value) VALUES (?, ?, ?)",
                  (user_id, 'blacklist', text))
        await event.reply("✅ Word added to blacklist!")
        clear_user_state(user_id)
    
    # Handle whitelist input
    elif state == "awaiting_whitelist":
        db_execute("INSERT OR REPLACE INTO filters (user_id, type, value) VALUES (?, ?, ?)",
                  (user_id, 'whitelist', text))
        await event.reply("✅ Word added to whitelist!")
        clear_user_state(user_id)
    
    # Handle delay input
    elif state == "awaiting_delay":
        if text.isdigit():
            delay_seconds = int(text)
            db_execute("INSERT OR REPLACE INTO delay_config (user_id, delay_seconds) VALUES (?, ?)",
                      (user_id, delay_seconds))
            await event.reply(f"✅ Delay set to {delay_seconds} seconds!")
        else:
            await event.reply("❌ Please enter a valid number of seconds.")
        clear_user_state(user_id)
    
    # Handle filter user input
    elif state == "awaiting_filter_user":
        if text.isdigit():
            user_to_whitelist = int(text)
            db_execute("INSERT OR REPLACE INTO whitelist_users (user_id, allowed_user_id) VALUES (?, ?)",
                      (user_id, user_to_whitelist))
            await event.reply(f"✅ User {user_to_whitelist} added to whitelist!")
        else:
            await event.reply("❌ Please enter a valid user ID.")
        clear_user_state(user_id)

# Handle forwarded messages for chat setup
@bot.on(events.NewMessage(func=lambda e: e.is_private and e.message.forward))
async def handle_forwarded_messages(event):
    user_id = event.sender_id
    state, data = get_user_state(user_id)
    
    if not state:
        return
    
    if state == "awaiting_incoming" and event.message.forward:
        try:
            # Try to get the original chat
            if hasattr(event.message.forward, 'chat_id'):
                chat_id = event.message.forward.chat_id
                # Get chat details using user's client
                user_client = await get_user_client(user_id)
                if user_client:
                    chat = await user_client.get_entity(chat_id)
                    title = getattr(chat, 'title', f"Chat {chat_id}")
                    
                    db_execute("INSERT OR REPLACE INTO incoming_chats (user_id, chat_id, title) VALUES (?, ?, ?)",
                              (user_id, chat_id, title))
                    
                    await event.reply(f"✅ Source chat set: {title} (ID: {chat_id})")
                    clear_user_state(user_id)
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease try again.")
    
    elif state == "awaiting_outgoing" and event.message.forward:
        try:
            # Try to get the original chat
            if hasattr(event.message.forward, 'chat_id'):
                chat_id = event.message.forward.chat_id
                # Get chat details using user's client
                user_client = await get_user_client(user_id)
                if user_client:
                    chat = await user_client.get_entity(chat_id)
                    title = getattr(chat, 'title', f"Chat {chat_id}")
                    
                    db_execute("INSERT OR REPLACE INTO outgoing_chats (user_id, chat_id, title) VALUES (?, ?, ?)",
                              (user_id, chat_id, title))
                    
                    await event.reply(f"✅ Target chat set: {title} (ID: {chat_id})")
                    clear_user_state(user_id)
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease try again.")
    
    elif state == "awaiting_filter_user" and event.message.forward:
        try:
            # Try to get the original user
            if hasattr(event.message.forward, 'from_id'):
                user_to_whitelist = event.message.forward.from_id.user_id
                db_execute("INSERT OR REPLACE INTO whitelist_users (user_id, allowed_user_id) VALUES (?, ?)",
                          (user_id, user_to_whitelist))
                await event.reply(f"✅ User {user_to_whitelist} added to whitelist!")
                clear_user_state(user_id)
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}\nPlease try again.")

# Handle text-based chat IDs for incoming/outgoing setup
@bot.on(events.NewMessage(func=lambda e: e.is_private and not e.message.text.startswith('/')))
async def handle_chat_id_input(event):
    user_id = event.sender_id
    state, data = get_user_state(user_id)
    text = event.message.text
    
    if state in ["awaiting_incoming", "awaiting_outgoing"]:
        try:
            # Try to resolve the chat by username or ID
            user_client = await get_user_client(user_id)
            if user_client:
                chat = await user_client.get_entity(text)
                chat_id = chat.id
                title = getattr(chat, 'title', f"Chat {chat_id}")
                
                if state == "awaiting_incoming":
                    db_execute("INSERT OR REPLACE INTO incoming_chats (user_id, chat_id, title) VALUES (?, ?, ?)",
                              (user_id, chat_id, title))
                    await event.reply(f"✅ Source chat set: {title} (ID: {chat_id})")
                else:
                    db_execute("INSERT OR REPLACE INTO outgoing_chats (user_id, chat_id, title) VALUES (?, ?, ?)",
                              (user_id, chat_id, title))
                    await event.reply(f"✅ Target chat set: {title} (ID: {chat_id})")
                
                clear_user_state(user_id)
        except Exception as e:
            await event.reply(f"❌ Error: Could not find chat '{text}'. Please make sure the chat exists and you have access to it.")

# Get user client session
async def get_user_client(user_id):
    if user_id in user_clients:
        return user_clients[user_id]
    
    result = db_fetchone("SELECT session_string FROM users WHERE user_id = ? AND authorized = 1", (user_id,))
    if result:
        session_string = result[0]
        api_result = db_fetchone("SELECT value FROM config WHERE user_id = ? AND key = 'api_id'", (user_id,))
        api_hash_result = db_fetchone("SELECT value FROM config WHERE user_id = ? AND key = 'api_hash'", (user_id,))
        
        if api_result and api_hash_result:
            api_id = int(api_result[0])
            api_hash = api_hash_result[0]
            
            user_client = TelegramClient(StringSession(session_string), api_id, api_hash)
            user_clients[user_id] = user_client
            return user_client
    
    return None

# Broadcasting command - Only for admin
@bot.on(events.NewMessage(pattern='/broadcasting'))
async def broadcasting_command(event):
    user_id = event.sender_id
    
    # Check if user is admin
    if not is_admin(user_id):
        await event.reply("❌ This command is only available for administrators.")
        return
    
    set_user_state(user_id, "awaiting_broadcast")
    await event.reply("📢 **Broadcast Mode**\n\nPlease send the message you want to broadcast to all users. It can be text, image, video, or any media.")

# Handle broadcast messages
@bot.on(events.NewMessage(func=lambda e: e.is_private))
async def handle_broadcast_messages(event):
    user_id = event.sender_id
    state, data = get_user_state(user_id)
    
    if state == "awaiting_broadcast" and is_admin(user_id):
        try:
            # Get all authorized users
            users = get_all_authorized_users()
            success_count = 0
            fail_count = 0
            
            await event.reply(f"📤 Starting broadcast to {len(users)} users...")
            
            # Send to each user
            for user in users:
                try:
                    # Forward the message to the user
                    await event.forward_to(user)
                    success_count += 1
                    
                    # Add a small delay to avoid rate limiting
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"Failed to send to user {user}: {e}")
                    fail_count += 1
            
            # Send broadcast report
            report_text = f"""
✅ **Broadcast Completed**

📊 **Report:**
• Total Users: {len(users)}
• Successful: {success_count}
• Failed: {fail_count}

🎯 **Success Rate:** {round((success_count/len(users))*100, 2)}%
"""
            await event.reply(report_text)
            clear_user_state(user_id)
            
        except Exception as e:
            await event.reply(f"❌ Broadcast error: {str(e)}")
            clear_user_state(user_id)

# Run the bot with proper event loop handling
def main():
    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        with bot:
            bot.start(bot_token=BOT_TOKEN)
            print("Bot started...")
            bot.run_until_disconnected()
    except KeyboardInterrupt:
        print("Bot stopped by user")
    finally:
        loop.close()

if __name__ == "__main__":
    main()