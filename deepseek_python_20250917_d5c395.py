from flask import Flask
import threading
import os
import time

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ 𝑇𝑟𝑦𝑖𝑛𝑔 𝑇𝑜 𝑇𝑎𝑐𝑘𝑙𝑒 𝑆𝑒𝑡𝑏𝑎𝑐𝑘 𝑇𝐺 - @MrJaggiX!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)

# Flask ko background thread me start karo
threading.Thread(target=run_flask, daemon=True).start()

# Performance optimization imports and settings
import asyncio
from concurrent.futures import ThreadPoolExecutor
import aiosqlite
from telethon.sessions import StringSession
from telethon import TelegramClient, events
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import sqlite3
import re
from collections import defaultdict

# Performance tuning
MAX_CONCURRENT_FORWARDS = 15  # Increased concurrent operations
BATCH_DELETE_SIZE = 20        # Batch size for delete operations
DB_BATCH_COMMIT_SIZE = 10     # How many operations before committing to DB

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

# DB setup with performance optimizations
def init_db():
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    
    # Enable WAL mode for better concurrency
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA cache_size=-2000")  # 2MB cache
    
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
    
    # Add indexes for faster queries
    c.execute('''CREATE INDEX IF NOT EXISTS idx_message_mapping_source 
                 ON message_mapping(source_channel_id, source_message_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_message_mapping_target 
                 ON message_mapping(target_channel_id, target_message_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_channel_pairs_source 
                 ON channel_pairs(source_id)''')
    
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('delete_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('text_only', 'false')")
    
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
        self.last_processed_message = {}  # Track last processed message per channel
        self.pending_operations = asyncio.Queue()
        self.processing_task = None
        self.db_batch = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_FORWARDS)
        
    def start_processing(self):
        """Start the background processing task"""
        if not self.processing_task:
            self.processing_task = asyncio.create_task(self.process_batch_operations())
            
    async def process_batch_operations(self):
        """Process database operations in batches for better performance"""
        while True:
            try:
                # Wait for operations or timeout
                operations = []
                try:
                    # Get first operation with timeout
                    op = await asyncio.wait_for(self.pending_operations.get(), timeout=0.5)
                    operations.append(op)
                    
                    # Try to get more operations without blocking
                    for _ in range(DB_BATCH_COMMIT_SIZE - 1):
                        try:
                            op = self.pending_operations.get_nowait()
                            operations.append(op)
                        except asyncio.QueueEmpty:
                            break
                except asyncio.TimeoutError:
                    # No operations, check if we have pending batch to commit
                    if self.db_batch:
                        await self.commit_db_batch()
                    continue
                
                # Add to batch and commit if batch size reached
                self.db_batch.extend(operations)
                if len(self.db_batch) >= DB_BATCH_COMMIT_SIZE:
                    await self.commit_db_batch()
                    
            except Exception as e:
                logger.error(f"Error in batch processing: {e}")
                
    async def commit_db_batch(self):
        """Commit a batch of database operations"""
        if not self.db_batch:
            return
            
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            for op_type, params in self.db_batch:
                if op_type == 'save_mapping':
                    c.execute("INSERT OR REPLACE INTO message_mapping (source_message_id, source_channel_id, target_message_id, target_channel_id) VALUES (?, ?, ?, ?)", params)
                elif op_type == 'delete_mapping':
                    if len(params) == 3:
                        c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=? AND target_channel_id=?", params)
                    else:
                        c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=?", params)
            
            conn.commit()
            self.db_batch = []
        except Exception as e:
            logger.error(f"Error committing batch: {e}")
        finally:
            conn.close()
        
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
        # Add to batch processing instead of immediate DB operation
        if self.processing_task:
            self.pending_operations.put_nowait(('save_mapping', (source_message_id, source_channel_id, target_message_id, target_channel_id)))
        
        # Update in-memory mapping immediately
        if source_channel_id not in self.message_mapping:
            self.message_mapping[source_channel_id] = {}
        
        if source_message_id not in self.message_mapping[source_channel_id]:
            self.message_mapping[source_channel_id][source_message_id] = {}
            
        self.message_mapping[source_channel_id][source_message_id][target_channel_id] = target_message_id
        return True
        
    def delete_message_mapping(self, source_message_id, source_channel_id, target_channel_id=None):
        # Add to batch processing
        if self.processing_task:
            if target_channel_id:
                self.pending_operations.put_nowait(('delete_mapping', (source_message_id, source_channel_id, target_channel_id)))
            else:
                self.pending_operations.put_nowait(('delete_mapping', (source_message_id, source_channel_id)))
        
        # Update in-memory mapping immediately
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
        
        c.execute("SELECT value FROM settings WHERE name='text_only'")
        result = c.fetchone()
        self.text_only = result and result[0] == 'true'
        
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
        elif name == 'text_only':
            self.text_only = value == 'true'
            
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

# ... [Keep all your command handlers as they are] ...

@client.on(events.NewMessage)
async def handle_channel_post(event):
    if not bot.forwarding_enabled:
        return
        
    # Check if this channel is in our pairs
    if event.chat_id in bot.channel_pairs:
        message = event.message
        original_text = message.text or message.raw_text or ""
        formatted_text = original_text
        
        # Text only mode check - agar text only mode on hai aur message media hai toh skip karo
        if bot.text_only and message.media:
            logger.info(f"Text only mode enabled, skipping media message: {message.id}")
            return
        
        # Check if we need to apply any replacements
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        c.execute("SELECT old_link, new_link FROM links")
        links = c.fetchall()
        conn.close()
        
        has_replacements = False
        if edits or links:
            for old, new in edits:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    has_replacements = True
                    
            for old, new in links:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    has_replacements = True
        
        # Send to all target channels for this source with concurrency control
        target_ids = bot.channel_pairs[event.chat_id]
        
        # Use semaphore to limit concurrent operations
        async with bot.semaphore:
            # Process all targets concurrently
            tasks = []
            for target_id in target_ids:
                # Check if message should be forwarded based on filter
                if not bot.should_forward_message(formatted_text, event.chat_id, target_id):
                    logger.info(f"Message not forwarded to {target_id} due to filter settings")
                    continue
                
                # Create task for each target
                task = asyncio.create_task(
                    forward_to_target(message, formatted_text, event.chat_id, target_id)
                )
                tasks.append(task)
            
            # Wait for all forwarding tasks to complete
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

async def forward_to_target(message, formatted_text, source_id, target_id):
    """Helper function to forward a message to a target channel"""
    try:
        # Text only mode mein media skip karo
        if bot.text_only and message.media:
            return
            
        # Handle media messages with captions
        if message.media and formatted_text:
            # Send media with the formatted caption
            sent_message = await client.send_file(
                target_id, 
                message.media, 
                caption=formatted_text
            )
            # Save the mapping between source and target messages
            if sent_message:
                bot.save_message_mapping(message.id, source_id, sent_message.id, target_id)
        elif message.media:
            # Send media without caption
            sent_message = await client.send_file(target_id, message.media)
            # Save the mapping between source and target messages
            if sent_message:
                bot.save_message_mapping(message.id, source_id, sent_message.id, target_id)
        elif formatted_text:
            # Send text message
            sent_message = await client.send_message(target_id, formatted_text)
            # Save the mapping between source and target messages
            if sent_message:
                bot.save_message_mapping(message.id, source_id, sent_message.id, target_id)
    except Exception as e:
        logger.error(f"Error sending message to {target_id}: {e}")
        # Fallback: try sending as plain text if media fails
        try:
            if formatted_text:
                sent_message = await client.send_message(target_id, formatted_text)
                # Save the mapping between source and target messages
                if sent_message:
                    bot.save_message_mapping(message.id, source_id, sent_message.id, target_id)
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")

# Handle message edits
@client.on(events.MessageEdited)
async def handle_message_edit(event):
    if not bot.edit_sync or not bot.forwarding_enabled:
        return
        
    # Check if this channel is in our pairs and we have a mapping for this message
    if (event.chat_id in bot.message_mapping and 
        event.message.id in bot.message_mapping[event.chat_id]):
        
        message = event.message
        original_text = message.text or message.raw_text or ""
        formatted_text = original_text
        
        # Apply replacements if any
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        c.execute("SELECT old_link, new_link FROM links")
        links = c.fetchall()
        conn.close()
        
        if edits or links:
            for old, new in edits:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    
            for old, new in links:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
        
        # Edit all target messages concurrently
        target_mappings = bot.message_mapping[event.chat_id][event.message.id]
        tasks = []
        for target_channel_id, target_message_id in target_mappings.items():
            task = asyncio.create_task(
                client.edit_message(target_channel_id, target_message_id, formatted_text)
            )
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Handle message deletions with batch processing
@client.on(events.MessageDeleted)
async def handle_message_delete(event):
    if not bot.delete_sync or not bot.forwarding_enabled:
        return
        
    # Process deletions in batches for better performance
    deleted_ids = event.deleted_ids
    
    for i in range(0, len(deleted_ids), BATCH_DELETE_SIZE):
        batch = deleted_ids[i:i+BATCH_DELETE_SIZE]
        
        # Process this batch
        tasks = []
        for deleted_message in batch:
            # Check if we have a mapping for this deleted message
            for source_channel_id, messages in bot.message_mapping.items():
                if deleted_message in messages:
                    # Delete all target messages
                    target_mappings = messages[deleted_message]
                    for target_channel_id, target_message_id in target_mappings.items():
                        task = asyncio.create_task(
                            client.delete_messages(target_channel_id, target_message_id)
                        )
                        tasks.append(task)
                    
                    # Remove the mapping
                    bot.delete_message_mapping(deleted_message, source_channel_id)
        
        # Wait for this batch to complete before processing next
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

async def main():
    print("Building app and starting client...")
    app = Application.builder().token(TOKEN).build()

    # Add all your command handlers here...
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("forward", forward_on_off))
    # ... [add all other command handlers] ...

    # Start the batch processing task
    bot.start_processing()
    
    # Start the Telethon client first
    await client.start()
    print("Telethon client started")
    
    # Start the Telegram bot
    await app.initialize()
    await app.start()
    print("Telegram bot started")

    # Run both
    await asyncio.gather(
        client.run_until_disconnected(),
        app.updater.start_polling()
    )

if __name__ == "__main__":
    # Create a new event loop for Windows compatibility
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
        # Commit any remaining batch operations before exiting
        if bot.db_batch:
            loop.run_until_complete(bot.commit_db_batch())
    except Exception as e:
        print(f"Error: {e}")
    finally:
        loop.close()