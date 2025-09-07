from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ 𝑇𝑟𝑦𝑖𝑛𝑔 𝑇𝑜 𝑇𝑎𝑐𝑘𝑙𝑒 𝑆𝑒𝑡𝑏𝑎𝑐𝑘 𝑇𝐺 - @MrJaggiX!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)

# Flask ko background thread me start karo
threading.Thread(target=run_flask).start()

import os
from telethon.sessions import StringSession
from telethon import TelegramClient, events
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import sqlite3
import re
from collections import defaultdict

api_id = int(os.getenv("API_ID")) 
api_hash = os.getenv("API_HASH")

# Session string from environment variable
session_str = os.getenv("SESSION_STRING") 
client = TelegramClient(StringSession(session_str), api_id, api_hash)

# Bot token
TOKEN = os.getenv("BOT_TOKEN")

# Your Telegram User ID (replace with your actual ID)
OWNER_USER_ID = int(os.getenv("ADMIN_USER_ID"))

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# DB setup
def init_db():
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS channel_pairs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_id INTEGER,
                  target_id INTEGER,
                  filter_keywords TEXT,
                  UNIQUE(source_id, target_id))''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS edits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  old_text TEXT,
                  new_text TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS links
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  old_link TEXT,
                  new_link TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  value TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER UNIQUE,
                  username TEXT,
                  is_owner BOOLEAN DEFAULT FALSE)''')
    
    # Add message mapping table to track forwarded messages
    c.execute('''CREATE TABLE IF NOT EXISTS message_mapping
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_message_id INTEGER,
                  source_channel_id INTEGER,
                  target_message_id INTEGER,
                  target_channel_id INTEGER,
                  UNIQUE(source_message_id, source_channel_id, target_channel_id))''')
    
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('delete_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forward_images', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forward_videos', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forward_audio', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forward_stickers', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forward_documents', 'true')")
    
    # Add yourself as the owner
    c.execute("INSERT OR IGNORE INTO admins (user_id, username, is_owner) VALUES (?, ?, ?)", 
              (OWNER_USER_ID, "Owner", True))
    
    conn.commit()
    conn.close()

init_db()

class ForwardBot:
    def __init__(self):
        self.channel_pairs = {}
        self.channel_filters = {}  # Store filter keywords for each channel pair
        self.message_mapping = defaultdict(dict)  # source_channel_id -> {source_message_id: {target_channel_id: target_message_id}}
        self.load_settings()
        self.load_channel_pairs()
        self.load_message_mapping()
        
    def load_channel_pairs(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_id, target_id, filter_keywords FROM channel_pairs")
        results = c.fetchall()
        conn.close()
        
        self.channel_pairs = {}
        self.channel_filters = {}
        for source_id, target_id, filter_keywords in results:
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
                self.channel_filters[source_id] = {}
                
            self.channel_pairs[source_id].append(target_id)
            self.channel_filters[source_id][target_id] = filter_keywords
            
    def load_message_mapping(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_message_id, source_channel_id, target_message_id, target_channel_id FROM message_mapping")
        results = c.fetchall()
        conn.close()
        
        self.message_mapping = defaultdict(dict)
        for source_msg_id, source_chan_id, target_msg_id, target_chan_id in results:
            if source_chan_id not in self.message_mapping:
                self.message_mapping[source_chan_id] = {}
            
            if source_msg_id not in self.message_mapping[source_chan_id]:
                self.message_mapping[source_chan_id][source_msg_id] = {}
                
            self.message_mapping[source_chan_id][source_msg_id][target_chan_id] = target_msg_id
            
    def save_message_mapping(self, source_message_id, source_channel_id, target_message_id, target_channel_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO message_mapping (source_message_id, source_channel_id, target_message_id, target_channel_id) VALUES (?, ?, ?, ?)",
                      (source_message_id, source_channel_id, target_message_id, target_channel_id))
            conn.commit()
            
            if source_channel_id not in self.message_mapping:
                self.message_mapping[source_channel_id] = {}
            
            if source_message_id not in self.message_mapping[source_channel_id]:
                self.message_mapping[source_channel_id][source_message_id] = {}
                
            self.message_mapping[source_channel_id][source_message_id][target_channel_id] = target_message_id
            
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def delete_message_mapping(self, source_message_id, source_channel_id, target_channel_id=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        if target_channel_id:
            c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=? AND target_channel_id=?", 
                     (source_message_id, source_channel_id, target_channel_id))
        else:
            c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=?", 
                     (source_message_id, source_channel_id))
            
        conn.commit()
        conn.close()
        
        if source_channel_id in self.message_mapping and source_message_id in self.message_mapping[source_channel_id]:
            if target_channel_id:
                if target_channel_id in self.message_mapping[source_channel_id][source_message_id]:
                    del self.message_mapping[source_channel_id][source_message_id][target_channel_id]
                    if not self.message_mapping[source_channel_id][source_message_id]:
                        del self.message_mapping[source_channel_id][source_message_id]
            else:
                del self.message_mapping[source_channel_id][source_message_id]
                
    def load_settings(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        c.execute("SELECT value FROM settings WHERE name='forwarding_enabled'")
        result = c.fetchone()
        self.forwarding_enabled = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='edit_sync'")
        result = c.fetchone()
        self.edit_sync = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='delete_sync'")
        result = c.fetchone()
        self.delete_sync = result and result[0] == 'true'
        
        # Load media forwarding settings
        c.execute("SELECT value FROM settings WHERE name='forward_images'")
        result = c.fetchone()
        self.forward_images = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='forward_videos'")
        result = c.fetchone()
        self.forward_videos = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='forward_audio'")
        result = c.fetchone()
        self.forward_audio = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='forward_stickers'")
        result = c.fetchone()
        self.forward_stickers = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='forward_documents'")
        result = c.fetchone()
        self.forward_documents = result and result[0] == 'true'
        
        conn.close()

    def add_channel_pair(self, source_id, target_id, filter_keywords=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO channel_pairs (source_id, target_id, filter_keywords) VALUES (?, ?, ?)",
                      (source_id, target_id, filter_keywords))
            conn.commit()
            
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
                self.channel_filters[source_id] = {}
                
            self.channel_pairs[source_id].append(target_id)
            self.channel_filters[source_id][target_id] = filter_keywords
            
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def update_channel_filter(self, source_id, target_id, filter_keywords):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("UPDATE channel_pairs SET filter_keywords = ? WHERE source_id = ? AND target_id = ?",
                      (filter_keywords, source_id, target_id))
            conn.commit()
            
            if source_id in self.channel_filters and target_id in self.channel_filters[source_id]:
                self.channel_filters[source_id][target_id] = filter_keywords
                
            success = True
        except Exception as e:
            print(f"Error updating filter: {e}")
            success = False
        conn.close()
        return success
        
    def remove_channel_pair(self, source_id, target_id=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        if target_id:
            c.execute("DELETE FROM channel_pairs WHERE source_id=? AND target_id=?", (source_id, target_id))
        else:
            c.execute("DELETE FROM channel_pairs WHERE source_id=?", (source_id,))
            
        conn.commit()
        conn.close()
        
        if source_id in self.channel_pairs:
            if target_id:
                if target_id in self.channel_pairs[source_id]:
                    self.channel_pairs[source_id].remove(target_id)
                    if not self.channel_pairs[source_id]:
                        del self.channel_pairs[source_id]
                        
                if source_id in self.channel_filters and target_id in self.channel_filters[source_id]:
                    del self.channel_filters[source_id][target_id]
                    if not self.channel_filters[source_id]:
                        del self.channel_filters[source_id]
            else:
                del self.channel_pairs[source_id]
                if source_id in self.channel_filters:
                    del self.channel_filters[source_id]
            
    def get_all_channel_pairs(self):
        pairs = []
        for source_id, target_ids in self.channel_pairs.items():
            for target_id in target_ids:
                filter_keywords = self.channel_filters.get(source_id, {}).get(target_id, None)
                pairs.append((source_id, target_id, filter_keywords))
        return pairs
        
    def set_setting(self, name, value):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                  (name, value))
        conn.commit()
        conn.close()
        
        if name == 'forwarding_enabled':
            self.forwarding_enabled = value == 'true'
        elif name == 'edit_sync':
            self.edit_sync = value == 'true'
        elif name == 'delete_sync':
            self.delete_sync = value == 'true'
        elif name == 'forward_images':
            self.forward_images = value == 'true'
        elif name == 'forward_videos':
            self.forward_videos = value == 'true'
        elif name == 'forward_audio':
            self.forward_audio = value == 'true'
        elif name == 'forward_stickers':
            self.forward_stickers = value == 'true'
        elif name == 'forward_documents':
            self.forward_documents = value == 'true'
            
    def is_admin(self, user_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
        
    def is_owner(self, user_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=? AND is_owner=TRUE", (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
        
    def add_admin(self, user_id, username):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO admins (user_id, username) VALUES (?, ?)", 
                     (user_id, username))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def remove_admin(self, user_id):
        if self.is_owner(user_id):
            return False
            
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
        
    def get_all_admins(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username, is_owner FROM admins")
        admins = c.fetchall()
        conn.close()
        return admins
        
    def should_forward_message(self, message_text, source_id, target_id):
        # If no filter is set, forward all messages
        if source_id not in self.channel_filters or target_id not in self.channel_filters[source_id]:
            return True
            
        filter_keywords = self.channel_filters[source_id][target_id]
        if not filter_keywords or filter_keywords.strip() == "":
            return True
            
        # Check if message contains any of the filter keywords
        keywords = [kw.strip() for kw in filter_keywords.split(",") if kw.strip()]
        message_lower = message_text.lower() if message_text else ""
        
        for keyword in keywords:
            if keyword.lower() in message_lower:
                return True
                
        return False

bot = ForwardBot()

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_admin(user_id):
            await update.message.reply_text("➢𝑌𝑜𝑢 𝐴𝑟𝑒 𝑁𝑜𝑡 𝐴𝑢𝑡ℎ𝑜𝑟𝑖𝑠𝑒𝑑 𝑡𝑜 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝐶𝑜𝑚𝑚𝑎𝑛𝑑 🤓🤝")
            return
        return await func(update, context)
    return wrapper

def owner_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_owner(user_id):
            await update.message.reply_text("➢𝑂𝑛𝑙𝑦 𝑡ℎ𝑒 𝑏𝑜𝑡 𝑜𝑤𝑛𝑒𝑟 𝑐𝑎𝑛 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝑐𝑜𝑚𝑚𝑎𝑛𝑑 🎗")
            return
        return await func(update, context)
    return wrapper

@admin_required
async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        command_text = message_text.replace('/add_edit', '').replace('/addword', '').strip()
        
        if '/' not in command_text:
            await update.message.reply_text("↳ Format: /addword old_text/new_text")
            return
            
        old_text, new_text = command_text.split('/', 1)
        old_text = old_text.strip()
        new_text = new_text.strip()
        
        if not old_text or not new_text:
            await update.message.reply_text("↳ Both old_text and new_text required")
            return
        
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (old_text, new_text))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Replacement added:\n{old_text} → {new_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        command_text = message_text.replace('/addlink', '').strip()
        
        if ' ' in command_text:
            parts = command_text.split(' ', 1)
            old_link = parts[0].strip()
            new_link = parts[1].strip()
        else:
            await update.message.reply_text("↳ Format: /addlink old_link new_link")
            return
        
        if not old_link or not new_link:
            await update.message.reply_text("❌ Both links required")
            return
        
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO links (old_link, new_link) VALUES (?, ?)", (old_link, new_link))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Link replacement added:\n{old_link} → {new_link}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removeword old_text")
            return

        old_text = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM edits WHERE old_text=?", (old_text,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Replacement removed: {old_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removelink old_link")
            return

        old_link = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM links WHERE old_link=?", (old_link,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Link replacement removed: {old_link}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def show_edits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("SELECT old_text, new_text FROM edits")
    edits = c.fetchall()
    
    c.execute("SELECT old_link, new_link FROM links")
    links = c.fetchall()
    conn.close()

    if not edits and not links:
        await update.message.reply_text("❌ No active replacements found")
        return

    response = "📜 Active Replacements:\n\n"
    
    if edits:
        response += "📝 Text Replacements:\n" + "\n".join([f"{old} → {new}" for old, new in edits]) + "\n\n"
    
    if links:
        response += "🔗 Link Replacements:\n" + "\n".join([f"{old} → {new}" for old, new in links])

    await update.message.reply_text(response)

@admin_required
async def forward_on_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
            await update.message.reply_text(f"📊 Forwarding Status: {status}")
            return
            
        status = context.args[0].lower()
        if status not in ['on', 'off']:
            await update.message.reply_text("➢ Format: /forward on or /forward off")
            return
            
        new_status = status == 'on'
        bot.set_setting('forwarding_enabled', 'true' if new_status else 'false')
        
        status_text = "ON ✅" if new_status else "OFF ❌"
        await update.message.reply_text(f"✅ Forwarding turned {status_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.set_setting('forwarding_enabled', 'false')
    await update.message.reply_text("🛑 Forwarding stopped")

@admin_required
async def check_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
    edit_status = "ON ✅" if bot.edit_sync else "OFF ❌"
    delete_status = "ON ✅" if bot.delete_sync else "OFF ❌"
    images_status = "ON ✅" if bot.forward_images else "OFF ❌"
    videos_status = "ON ✅" if bot.forward_videos else "OFF ❌"
    audio_status = "ON ✅" if bot.forward_audio else "OFF ❌"
    stickers_status = "ON ✅" if bot.forward_stickers else "OFF ❌"
    documents_status = "ON ✅" if bot.forward_documents else "OFF ❌"
    
    channel_pairs = bot.get_all_channel_pairs()
    if channel_pairs:
        channels_text = "\n".join([f"Source: {src} → Target: {tgt} | Filter: {filt if filt else 'None'}" for src, tgt, filt in channel_pairs])
        await update.message.reply_text(
            f"⚙️ Settings:\n"
            f"Forwarding: {status}\n"
            f"Edit Sync: {edit_status}\n"
            f"Delete Sync: {delete_status}\n"
            f"Images: {images_status}\n"
            f"Videos: {videos_status}\n"
            f"Audio: {audio_status}\n"
            f"Stickers: {stickers_status}\n"
            f"Documents: {documents_status}\n\n"
            f"📡 Channel Pairs:\n{channels_text}"
        )
    else:
        await update.message.reply_text("No channel pairs set up yet")

@owner_required
async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("DELETE FROM channel_pairs")
    c.execute("DELETE FROM edits")
    c.execute("DELETE FROM links")
    c.execute("DELETE FROM settings")
    c.execute("DELETE FROM message_mapping")
    
    c.execute("INSERT INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT INTO settings (name, value) VALUES ('delete_sync', 'false')")
    c.execute("INSERT INTO settings (name, value) VALUES ('forward_images', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('forward_videos', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('forward_audio', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('forward_stickers', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('forward_documents', 'true')")
    
    conn.commit()
    conn.close()
    
    bot.load_channel_pairs()
    bot.load_settings()
    bot.load_message_mapping()
    
    await update.message.reply_text("✅ All settings reset successfully")

@admin_required
async def add_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("➢ Format: /addpair source_channel_id target_channel_id [filter_keywords]")
            await update.message.reply_text("📝 Example: /addpair -100123456789 -100987654321 keyword1,keyword2")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1])
        
        # Check if filter keywords are provided
        filter_keywords = ' '.join(context.args[2:]) if len(context.args) > 2 else None
        
        success = bot.add_channel_pair(source_id, target_id, filter_keywords)
        if success:
            if filter_keywords:
                await update.message.reply_text(f"✅ Channel pair added with filter:\nSource: {source_id} → Target: {target_id}\nFilter: {filter_keywords}")
            else:
                await update.message.reply_text(f"✅ Channel pair added:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text("😃 This channel pair already exists")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def set_channel_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("➢ Format: /setfilter source_channel_id target_channel_id filter_keywords")
            await update.message.reply_text("📝 Example: /setfilter -100123456789 -100987654321 keyword1,keyword2,keyword3")
            await update.message.reply_text("📝 To remove filter: /setfilter source_channel_id target_channel_id none")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1])
        
        # Check if the channel pair exists
        if source_id not in bot.channel_pairs or target_id not in bot.channel_pairs[source_id]:
            await update.message.reply_text("🥱 Channel pair does not exist")
            return
            
        # Get filter keywords
        filter_keywords = ' '.join(context.args[2:]) if len(context.args) > 2 else None
        
        # Handle "none" keyword to remove filter
        if filter_keywords and filter_keywords.lower() == "none":
            filter_keywords = None
            
        success = bot.update_channel_filter(source_id, target_id, filter_keywords)
        if success:
            if filter_keywords:
                await update.message.reply_text(f"✅ Filter updated:\nSource: {source_id} → Target: {target_id}\nFilter: {filter_keywords}")
            else:
                await update.message.reply_text(f"✅ Filter removed:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text("🥲 Error updating filter")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removepair source_channel_id [target_channel_id]")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1]) if len(context.args) > 1 else None
        
        bot.remove_channel_pair(source_id, target_id)
        
        if target_id:
            await update.message.reply_text(f"✅ Channel pair removed:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text(f"✅ All channel pairs removed for source: {source_id}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_channel_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_pairs = bot.get_all_channel_pairs()
    if channel_pairs:
        response = "📡 Channel Pairs:\n\n" + "\n".join([f"Source: {src} → Target: {tgt} | Filter: {filt if filt else 'None'}" for src, tgt, filt in channel_pairs])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("🥱 No channel pairs set up yet")

@admin_required
async def block_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /block text_to_block")
            return

        text_to_block = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (text_to_block, ''))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Content blocked: {text_to_block}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def toggle_edit_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.edit_sync
    bot.set_setting('edit_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Edit Sync turned {status_text}")

@admin_required
async def toggle_delete_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.delete_sync
    bot.set_setting('delete_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Delete Sync turned {status_text}")

# Media forwarding toggle commands
@admin_required
async def toggle_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.forward_images
    bot.set_setting('forward_images', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Image forwarding turned {status_text}")

@admin_required
async def toggle_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.forward_videos
    bot.set_setting('forward_videos', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Video forwarding turned {status_text}")

@admin_required
async def toggle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.forward_audio
    bot.set_setting('forward_audio', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Audio forwarding turned {status_text}")

@admin_required
async def toggle_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.forward_stickers
    bot.set_setting('forward_stickers', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Sticker forwarding turned {status_text}")

@admin_required
async def toggle_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.forward_documents
    bot.set_setting('forward_documents', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Document forwarding turned {status_text}")

@owner_required
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /addadmin user_id [username]")
            return
            
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else "Unknown"
        
        success = bot.add_admin(user_id, username)
        if success:
            await update.message.reply_text(f"✅ Admin added: {user_id} ({username})")
        else:
            await update.message.reply_text("🤔 This user is already an admin")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@owner_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removeadmin user_id")
            return
            
        user_id = int(context.args[0])
        success = bot.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Admin removed: {user_id}")
        else:
            await update.message.reply_text("😎 Cannot remove the owner or user not found")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = bot.get_all_admins()
    if admins:
        response = "👑 Admins:\n\n" + "\n".join([f"ID: {user_id}, Name: {username}{' (Owner)' if is_owner else ''}" for user_id, username, is_owner in admins])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("🤔 No admins found")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if bot.is_admin(user_id):
        await update.message.reply_text(
            "🤖 Auto Forward Bot is running!\n\n"
            "📋 Available Commands:\n"
            "/addpair - Add channel pair\n"
            "/removepair - Remove channel pair\n"
            "/setfilter - Set filter for channel pair\n"
            "/listpairs - List all channel pairs\n"
            "/forward - Toggle forwarding\n"
            "/editsync - Toggle edit sync\n"
            "/deletesync - Toggle delete sync\n"
            "/addword - Add text replacement\n"
            "/addlink - Add link replacement\n"
            "/removeword - Remove text replacement\n"
            "/removelink - Remove link replacement\n"
            "/showrepl - Show all replacements\n"
            "/block - Block specific content\n"
            "/settings - Show current settings\n"
            "/reset - Reset all settings (owner only)\n"
            "/addadmin - Add admin (owner only)\n"
            "/removeadmin - Remove admin (owner only)\n"
            "/listadmins - List all admins\n"
            "/toggleimages - Toggle image forwarding\n"
            "/togglevideos - Toggle video forwarding\n"
            "/toggleaudio - Toggle audio forwarding\n"
            "/togglestickers - Toggle sticker forwarding\n"
            "/toggledocuments - Toggle document forwarding"
        )
    else:
        await update.message.reply_text("❌ You are not authorized to use this bot")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Auto Forward Bot Help\n\n"
        "This bot automatically forwards messages from one channel to another with optional filtering and text replacement.\n\n"
        "📋 Main Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/addpair - Add a channel pair\n"
        "/removepair - Remove a channel pair\n"
        "/listpairs - List all channel pairs\n"
        "/forward - Toggle forwarding on/off\n"
        "/settings - Show current settings\n\n"
        "Contact the bot owner for more information."
    )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Unknown command. Use /help to see available commands.")

def apply_text_replacements(text):
    if not text:
        return text
        
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("SELECT old_text, new_text FROM edits")
    edits = c.fetchall()
    conn.close()
    
    for old_text, new_text in edits:
        text = text.replace(old_text, new_text)
        
    return text

def apply_link_replacements(text):
    if not text:
        return text
        
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("SELECT old_link, new_link FROM links")
    links = c.fetchall()
    conn.close()
    
    for old_link, new_link in links:
        text = text.replace(old_link, new_link)
        
    return text

def should_forward_media(message):
    if message.photo and not bot.forward_images:
        return False
    if message.video and not bot.forward_videos:
        return False
    if message.audio and not bot.forward_audio:
        return False
    if message.sticker and not bot.forward_stickers:
        return False
    if message.document and not bot.forward_documents:
        return False
    return True

@client.on(events.NewMessage)
async def handle_new_message(event):
    if not bot.forwarding_enabled:
        return
        
    message = event.message
    chat_id = event.chat_id
    
    # Check if this chat is a source channel
    if chat_id in bot.channel_pairs:
        # Check if this is a media message and if we should forward it
        if message.media and not should_forward_media(message):
            return
            
        message_text = message.text or message.caption or ""
        original_text = message_text
        
        # Apply text and link replacements
        message_text = apply_text_replacements(message_text)
        message_text = apply_link_replacements(message_text)
        
        for target_id in bot.channel_pairs[chat_id]:
            # Check if message should be forwarded based on filter
            if bot.should_forward_message(original_text, chat_id, target_id):
                try:
                    # Forward the message with media if present
                    if message.media:
                        # Forward media message with modified caption if needed
                        if message_text != original_text and message_text:
                            forwarded_msg = await client.send_file(
                                target_id,
                                file=message.media,
                                caption=message_text,
                                parse_mode='html'
                            )
                        else:
                            forwarded_msg = await client.forward_messages(target_id, message)
                    else:
                        # Forward text message with replacements
                        forwarded_msg = await client.send_message(target_id, message_text, parse_mode='html')
                    
                    # Save the message mapping for edit/delete sync
                    bot.save_message_mapping(message.id, chat_id, forwarded_msg.id, target_id)
                    
                except Exception as e:
                    print(f"Error forwarding message: {e}")

@client.on(events.MessageEdited)
async def handle_edit_message(event):
    if not bot.edit_sync:
        return
        
    message = event.message
    chat_id = event.chat_id
    
    # Check if this edited message is from a source channel and we have mappings
    if chat_id in bot.message_mapping and message.id in bot.message_mapping[chat_id]:
        message_text = message.text or message.caption or ""
        original_text = message_text
        
        # Apply text and link replacements
        message_text = apply_text_replacements(message_text)
        message_text = apply_link_replacements(message_text)
        
        # Update the message in all target channels
        for target_id, target_msg_id in bot.message_mapping[chat_id][message.id].items():
            try:
                if message.media:
                    # For media messages, we can only edit the caption
                    if message_text != original_text and message_text:
                        await client.edit_message(target_id, target_msg_id, message_text, parse_mode='html')
                else:
                    # For text messages, edit the content
                    await client.edit_message(target_id, target_msg_id, message_text, parse_mode='html')
            except Exception as e:
                print(f"Error syncing edit: {e}")

@client.on(events.MessageDeleted)
async def handle_delete_message(event):
    if not bot.delete_sync:
        return
        
    for chat_id, deleted_msg_ids in event.deleted_ids.items():
        # Check if any deleted messages are from a source channel we're tracking
        if chat_id in bot.message_mapping:
            for msg_id in deleted_msg_ids:
                if msg_id in bot.message_mapping[chat_id]:
                    # Delete the corresponding messages in target channels
                    for target_id, target_msg_id in bot.message_mapping[chat_id][msg_id].items():
                        try:
                            await client.delete_messages(target_id, target_msg_id)
                        except Exception as e:
                            print(f"Error syncing delete: {e}")
                    
                    # Remove the mapping
                    bot.delete_message_mapping(msg_id, chat_id)

def main():
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addpair", add_channel_pair))
    application.add_handler(CommandHandler("removepair", remove_channel_pair))
    application.add_handler(CommandHandler("setfilter", set_channel_filter))
    application.add_handler(CommandHandler("listpairs", list_channel_pairs))
    application.add_handler(CommandHandler("forward", forward_on_off))
    application.add_handler(CommandHandler("stop", stop_bot))
    application.add_handler(CommandHandler("settings", check_settings))
    application.add_handler(CommandHandler("reset", reset_all))
    application.add_handler(CommandHandler("addword", add_edit))
    application.add_handler(CommandHandler("addlink", add_link))
    application.add_handler(CommandHandler("removeword", remove_edit))
    application.add_handler(CommandHandler("removelink", remove_link))
    application.add_handler(CommandHandler("showrepl", show_edits))
    application.add_handler(CommandHandler("block", block_content))
    application.add_handler(CommandHandler("editsync", toggle_edit_sync))
    application.add_handler(CommandHandler("deletesync", toggle_delete_sync))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("listadmins", list_admins))
    
    # Media toggle commands
    application.add_handler(CommandHandler("toggleimages", toggle_images))
    application.add_handler(CommandHandler("togglevideos", toggle_videos))
    application.add_handler(CommandHandler("toggleaudio", toggle_audio))
    application.add_handler(CommandHandler("togglestickers", toggle_stickers))
    application.add_handler(CommandHandler("toggledocuments", toggle_documents))

    # Add handler for unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Start the Bot
    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == "__main__":
    # Start the client in a separate thread
    client.start()
    print("✅ Client started")
    
    # Run the main function
    main()