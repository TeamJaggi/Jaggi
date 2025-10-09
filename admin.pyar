import os
import json
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

# Configure logging
logging.basicConfig(level=logging.INFO, format='👑 %(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdminManager:
    def __init__(self, bot, db_path='bot_data.db'):
        self.bot = bot
        self.db_path = db_path
        self.admin_ids = self.load_admin_ids()
        self.force_sub_channels = self.load_force_sub_channels()
        self.welcome_settings = self.load_welcome_settings()
        self.broadcast_stats = {}
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    downloads_count INTEGER DEFAULT 0,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Force sub channels table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS force_sub_channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT,
                    channel_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Welcome settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    welcome_text TEXT,
                    image_url TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Broadcast history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS broadcast_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    message_text TEXT,
                    total_users INTEGER,
                    success_count INTEGER,
                    failed_count INTEGER,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
    
    def load_admin_ids(self):
        """Load admin IDs from file or environment"""
        try:
            if os.path.exists('admin_ids.json'):
                with open('admin_ids.json', 'r') as f:
                    return json.load(f).get('admin_ids', [])
            else:
                # Default admin (bot owner)
                default_admins = [6651946441]  # Replace with your Telegram ID
                self.save_admin_ids(default_admins)
                return default_admins
        except Exception as e:
            logger.error(f"❌ Error loading admin IDs: {e}")
            return []
    
    def save_admin_ids(self, admin_ids):
        """Save admin IDs to file"""
        try:
            with open('admin_ids.json', 'w') as f:
                json.dump({'admin_ids': admin_ids}, f, indent=4)
        except Exception as e:
            logger.error(f"❌ Error saving admin IDs: {e}")
    
    def load_force_sub_channels(self):
        """Load force subscription channels"""
        try:
            if os.path.exists('force_sub_channels.json'):
                with open('force_sub_channels.json', 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"❌ Error loading force sub channels: {e}")
            return {}
    
    def save_force_sub_channels(self):
        """Save force subscription channels"""
        try:
            with open('force_sub_channels.json', 'w') as f:
                json.dump(self.force_sub_channels, f, indent=4)
        except Exception as e:
            logger.error(f"❌ Error saving force sub channels: {e}")
    
    def load_welcome_settings(self):
        """Load welcome message settings"""
        try:
            if os.path.exists('welcome_settings.json'):
                with open('welcome_settings.json', 'r') as f:
                    return json.load(f)
            return {
                'enabled': True,
                'welcome_text': '✨ Welcome to the bot! 🎉',
                'image_url': None
            }
        except Exception as e:
            logger.error(f"❌ Error loading welcome settings: {e}")
            return {'enabled': True, 'welcome_text': '✨ Welcome to the bot! 🎉', 'image_url': None}
    
    def save_welcome_settings(self):
        """Save welcome message settings"""
        try:
            with open('welcome_settings.json', 'w') as f:
                json.dump(self.welcome_settings, f, indent=4)
        except Exception as e:
            logger.error(f"❌ Error saving welcome settings: {e}")
    
    def is_admin(self, user_id):
        """Check if user is admin"""
        return user_id in self.admin_ids
    
    # 🔧 ADMIN COMMAND HANDLERS
    
    def handle_admin_command(self, message):
        """Handle admin commands"""
        if not self.is_admin(message.from_user.id):
            self.bot.reply_to(message, "❌ <b>Access Denied!</b>\nYou are not authorized to use admin commands.")
            return
        
        command = message.text.split()[0].lower()
        
        if command == '/admin':
            self.show_admin_panel(message)
        elif command == '/broadcast':
            self.start_broadcast(message)
        elif command == '/stats':
            self.show_bot_stats(message)
        elif command == '/addadmin':
            self.add_admin(message)
        elif command == '/removeadmin':
            self.remove_admin(message)
        elif command == '/forceadd':
            self.add_force_sub(message)
        elif command == '/forceremove':
            self.remove_force_sub(message)
        elif command == '/setwelcome':
            self.set_welcome_message(message)
        elif command == '/users':
            self.manage_users(message)
    
    def show_admin_panel(self, message):
        """Show admin control panel"""
        admin_panel = """
👑 <b>ADMIN CONTROL PANEL</b>

📊 <b>Bot Statistics:</b>
• Total Users: <code>{total_users}</code>
• Active Today: <code>{active_today}</code>
• Total Downloads: <code>{total_downloads}</code>

⚙️ <b>Admin Commands:</b>

📢 <b>Broadcast System:</b>
<code>/broadcast</code> - Send message to all users
<code>/stats</code> - Detailed bot statistics

👥 <b>User Management:</b>
<code>/users</code> - Manage users list
<code>/forceadd</code> - Add force subscribe channel
<code>/forceremove</code> - Remove force subscribe channel

🛠️ <b>Bot Settings:</b>
<code>/setwelcome</code> - Set welcome message & image
<code>/addadmin</code> - Add new admin
<code>/removeadmin</code> - Remove admin

🔧 <b>Configuration:</b>
<code>/admin</code> - Show this panel
        """.format(
            total_users=self.get_total_users(),
            active_today=self.get_active_today(),
            total_downloads=self.get_total_downloads()
        )
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("🔗 Force Sub", callback_data="admin_force_sub"),
            InlineKeyboardButton("👋 Welcome Msg", callback_data="admin_welcome"),
            InlineKeyboardButton("🛠️ Admins", callback_data="admin_manage")
        )
        
        self.bot.send_message(message.chat.id, admin_panel, reply_markup=keyboard)
    
    # 📢 ADVANCED BROADCAST SYSTEM
    
    def start_broadcast(self, message):
        """Start broadcast process"""
        msg = self.bot.reply_to(message, 
            "📢 <b>BROADCAST SYSTEM</b>\n\n"
            "Please send the message you want to broadcast to all users.\n\n"
            "💡 <b>Supported formats:</b>\n"
            "• Text messages\n"
            "• Photos with captions\n"
            "• Documents\n"
            "• Videos\n\n"
            "⚠️ <i>This will be sent to all users. Proceed with caution.</i>"
        )
        
        self.bot.register_next_step_handler(msg, self.process_broadcast_message)
    
    def process_broadcast_message(self, message):
        """Process and send broadcast"""
        try:
            total_users = self.get_total_users()
            broadcast_id = f"broadcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store broadcast stats
            self.broadcast_stats[broadcast_id] = {
                'total': total_users,
                'success': 0,
                'failed': 0,
                'start_time': datetime.now(),
                'message_type': message.content_type
            }
            
            # Start broadcast in separate thread
            broadcast_thread = threading.Thread(
                target=self.send_broadcast,
                args=(broadcast_id, message, total_users)
            )
            broadcast_thread.start()
            
            # Show progress
            progress_msg = self.bot.send_message(
                message.chat.id,
                f"📤 <b>BROADCAST STARTED</b>\n\n"
                f"• Total Users: <code>{total_users}</code>\n"
                f"• Message Type: <code>{message.content_type}</code>\n"
                f"• Status: <code>Starting...</code>\n\n"
                f"⏳ <i>This may take several minutes...</i>"
            )
            
            # Monitor progress
            self.monitor_broadcast_progress(message.chat.id, progress_msg.message_id, broadcast_id)
            
        except Exception as e:
            logger.error(f"❌ Broadcast error: {e}")
            self.bot.reply_to(message, f"❌ Broadcast failed: {str(e)}")
    
    def send_broadcast(self, broadcast_id, original_message, total_users):
        """Send broadcast to all users"""
        try:
            user_ids = self.get_all_user_ids()
            success_count = 0
            failed_count = 0
            
            for index, user_id in enumerate(user_ids, 1):
                try:
                    if original_message.content_type == 'text':
                        self.bot.send_message(user_id, original_message.text, parse_mode='HTML')
                    elif original_message.content_type == 'photo':
                        self.bot.send_photo(
                            user_id, 
                            original_message.photo[-1].file_id,
                            caption=original_message.caption,
                            parse_mode='HTML'
                        )
                    elif original_message.content_type == 'document':
                        self.bot.send_document(
                            user_id,
                            original_message.document.file_id,
                            caption=original_message.caption,
                            parse_mode='HTML'
                        )
                    elif original_message.content_type == 'video':
                        self.bot.send_video(
                            user_id,
                            original_message.video.file_id,
                            caption=original_message.caption,
                            parse_mode='HTML'
                        )
                    
                    success_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Failed to send to {user_id}: {e}")
                
                # Update progress every 10 users
                if index % 10 == 0:
                    self.broadcast_stats[broadcast_id].update({
                        'success': success_count,
                        'failed': failed_count
                    })
                
                # Small delay to avoid rate limits
                import time
                time.sleep(0.1)
            
            # Final update
            self.broadcast_stats[broadcast_id].update({
                'success': success_count,
                'failed': failed_count,
                'completed': True
            })
            
            # Save to database
            self.save_broadcast_history(
                original_message.from_user.id,
                original_message.text or original_message.caption or f"[{original_message.content_type}]",
                total_users,
                success_count,
                failed_count
            )
            
        except Exception as e:
            logger.error(f"❌ Broadcast thread error: {e}")
    
    def monitor_broadcast_progress(self, chat_id, message_id, broadcast_id):
        """Monitor and update broadcast progress"""
        import time
        
        while broadcast_id in self.broadcast_stats:
            stats = self.broadcast_stats[broadcast_id]
            progress = (stats['success'] + stats['failed']) / stats['total'] * 100
            
            status_text = f"""
📤 <b>BROADCAST PROGRESS</b>

• Total Users: <code>{stats['total']}</code>
• Successful: <code>{stats['success']}</code> ✅
• Failed: <code>{stats['failed']}</code> ❌
• Progress: <code>{progress:.1f}%</code>

⏰ <i>Started: {stats['start_time'].strftime('%H:%M:%S')}</i>
            """
            
            if stats.get('completed'):
                status_text += f"\n✅ <b>BROADCAST COMPLETED!</b>"
                del self.broadcast_stats[broadcast_id]
            
            try:
                self.bot.edit_message_text(
                    status_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode='HTML'
                )
            except:
                pass
            
            if stats.get('completed'):
                break
            
            time.sleep(2)
    
    def save_broadcast_history(self, admin_id, message_text, total_users, success_count, failed_count):
        """Save broadcast to history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO broadcast_history 
                (admin_id, message_text, total_users, success_count, failed_count)
                VALUES (?, ?, ?, ?, ?)
            ''', (admin_id, message_text, total_users, success_count, failed_count))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error saving broadcast history: {e}")
    
    # 🔗 FORCE SUBSCRIPTION SYSTEM
    
    def add_force_sub(self, message):
        """Add force subscription channel"""
        try:
            parts = message.text.split()
            if len(parts) < 3:
                self.bot.reply_to(message,
                    "❌ <b>Invalid Format!</b>\n\n"
                    "Usage: <code>/forceadd channel_id @channel_username</code>\n\n"
                    "Example: <code>/forceadd -100123456789 @my_channel</code>"
                )
                return
            
            channel_id = parts[1]
            channel_username = parts[2] if parts[2].startswith('@') else f"@{parts[2]}"
            
            self.force_sub_channels[channel_id] = {
                'username': channel_username,
                'added_by': message.from_user.id,
                'added_date': datetime.now().isoformat()
            }
            
            self.save_force_sub_channels()
            
            # Save to database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO force_sub_channels 
                (channel_id, channel_name, channel_url) 
                VALUES (?, ?, ?)
            ''', (channel_id, channel_username, f"https://t.me/{channel_username[1:]}"))
            conn.commit()
            conn.close()
            
            self.bot.reply_to(message,
                f"✅ <b>Force Subscription Added!</b>\n\n"
                f"• Channel ID: <code>{channel_id}</code>\n"
                f"• Username: {channel_username}\n"
                f"• Users will need to join this channel"
            )
            
        except Exception as e:
            logger.error(f"❌ Error adding force sub: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    def remove_force_sub(self, message):
        """Remove force subscription channel"""
        try:
            parts = message.text.split()
            if len(parts) < 2:
                # Show current channels
                if not self.force_sub_channels:
                    self.bot.reply_to(message, "❌ No force subscription channels configured.")
                    return
                
                channels_list = "🔗 <b>Current Force Sub Channels:</b>\n\n"
                for channel_id, channel_data in self.force_sub_channels.items():
                    channels_list += f"• {channel_data['username']} (<code>{channel_id}</code>)\n"
                
                channels_list += "\nTo remove: <code>/forceremove channel_id</code>"
                self.bot.reply_to(message, channels_list)
                return
            
            channel_id = parts[1]
            if channel_id in self.force_sub_channels:
                removed_channel = self.force_sub_channels.pop(channel_id)
                self.save_force_sub_channels()
                
                # Remove from database
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM force_sub_channels WHERE channel_id = ?', (channel_id,))
                conn.commit()
                conn.close()
                
                self.bot.reply_to(message,
                    f"✅ <b>Force Subscription Removed!</b>\n\n"
                    f"• Channel: {removed_channel['username']}\n"
                    f"• ID: <code>{channel_id}</code>"
                )
            else:
                self.bot.reply_to(message, "❌ Channel ID not found in force subscription list.")
                
        except Exception as e:
            logger.error(f"❌ Error removing force sub: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    def check_user_subscription(self, user_id):
        """Check if user is subscribed to all required channels"""
        if not self.force_sub_channels:
            return True, []
        
        not_joined_channels = []
        
        for channel_id, channel_data in self.force_sub_channels.items():
            try:
                chat_member = self.bot.get_chat_member(channel_id, user_id)
                if chat_member.status in ['left', 'kicked']:
                    not_joined_channels.append(channel_data['username'])
            except Exception as e:
                logger.error(f"❌ Error checking subscription for {user_id}: {e}")
                not_joined_channels.append(channel_data['username'])
        
        return len(not_joined_channels) == 0, not_joined_channels
    
    # 👋 WELCOME MESSAGE SYSTEM
    
    def set_welcome_message(self, message):
        """Set welcome message and image"""
        try:
            parts = message.text.split(' ', 1)
            if len(parts) < 2:
                self.bot.reply_to(message,
                    "❌ <b>Invalid Format!</b>\n\n"
                    "Usage: <code>/setwelcome Your welcome message here</code>\n\n"
                    "💡 <b>Tips:</b>\n"
                    "• Use <code>{name}</code> for user's first name\n"
                    "• Use <code>{username}</code> for username\n"
                    "• Add image by sending it with caption after this command\n\n"
                    "Example: <code>/setwelcome 👋 Hello {name}! Welcome to our bot! ✨</code>"
                )
                return
            
            welcome_text = parts[1]
            self.welcome_settings['welcome_text'] = welcome_text
            self.welcome_settings['image_url'] = None  # Will be set if image is sent
            
            self.save_welcome_settings()
            
            # Ask for image
            msg = self.bot.reply_to(message,
                "✅ <b>Welcome text updated!</b>\n\n"
                "Now, you can send an image to set as welcome image (optional).\n"
                "Send any image with caption, or send <code>/skip</code> to continue without image."
            )
            
            self.bot.register_next_step_handler(msg, self.process_welcome_image)
            
        except Exception as e:
            logger.error(f"❌ Error setting welcome message: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    def process_welcome_image(self, message):
        """Process welcome image"""
        try:
            if message.content_type == 'photo':
                # Get the highest resolution photo
                file_id = message.photo[-1].file_id
                self.welcome_settings['image_url'] = file_id
                self.save_welcome_settings()
                
                self.bot.reply_to(message,
                    "🎉 <b>Welcome Message Complete!</b>\n\n"
                    "✅ Text message set\n"
                    "✅ Image set\n\n"
                    "Users will now see this welcome message when they start the bot."
                )
            else:
                self.bot.reply_to(message,
                    "✅ <b>Welcome Message Updated!</b>\n\n"
                    "Text message set (no image).\n"
                    "Users will see this welcome message."
                )
                
        except Exception as e:
            logger.error(f"❌ Error processing welcome image: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    def get_welcome_message(self, user_name, username):
        """Get formatted welcome message"""
        welcome_text = self.welcome_settings.get('welcome_text', '✨ Welcome! 🎉')
        image_url = self.welcome_settings.get('image_url')
        
        formatted_text = welcome_text.replace('{name}', user_name).replace('{username}', username or 'User')
        
        return formatted_text, image_url
    
    # 👥 USER MANAGEMENT
    
    def manage_users(self, message):
        """Show user management options"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📊 User Stats", callback_data="user_stats"),
            InlineKeyboardButton("👥 All Users", callback_data="all_users"),
            InlineKeyboardButton("📧 Export Users", callback_data="export_users"),
            InlineKeyboardButton("🔄 Update Database", callback_data="update_db")
        )
        
        stats_text = f"""
👥 <b>USER MANAGEMENT</b>

• Total Users: <code>{self.get_total_users()}</code>
• Active Today: <code>{self.get_active_today()}</code>
• New Today: <code>{self.get_new_today()}</code>
• Total Downloads: <code>{self.get_total_downloads()}</code>
        """
        
        self.bot.send_message(message.chat.id, stats_text, reply_markup=keyboard)
    
    # 📊 STATISTICS METHODS
    
    def get_total_users(self):
        """Get total number of users"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return 0
    
    def get_active_today(self):
        """Get users active today"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_active >= DATE("now")')
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return 0
    
    def get_new_today(self):
        """Get new users today"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users WHERE joined_date >= DATE("now")')
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return 0
    
    def get_total_downloads(self):
        """Get total downloads count"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(downloads_count) FROM users')
            total = cursor.fetchone()[0] or 0
            conn.close()
            return total
        except:
            return 0
    
    def get_all_user_ids(self):
        """Get all user IDs from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            user_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            return user_ids
        except:
            return []
    
    def show_bot_stats(self, message):
        """Show detailed bot statistics"""
        stats_text = f"""
📊 <b>DETAILED BOT STATISTICS</b>

👥 <b>User Statistics:</b>
• Total Users: <code>{self.get_total_users()}</code>
• Active Today: <code>{self.get_active_today()}</code>
• New Today: <code>{self.get_new_today()}</code>
• Total Downloads: <code>{self.get_total_downloads()}</code>

🔗 <b>Force Subscription:</b>
• Channels: <code>{len(self.force_sub_channels)}</code>

👑 <b>Administration:</b>
• Admins: <code>{len(self.admin_ids)}</code>
• Welcome Message: {'✅ Enabled' if self.welcome_settings.get('enabled', True) else '❌ Disabled'}

💾 <b>System:</b>
• Database: <code>Operational</code>
• Last Update: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>
        """
        
        self.bot.send_message(message.chat.id, stats_text)
    
    # 👑 ADMIN MANAGEMENT
    
    def add_admin(self, message):
        """Add new admin"""
        try:
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(message,
                    "❌ <b>Invalid Format!</b>\n\n"
                    "Usage: <code>/addadmin user_id</code>\n\n"
                    "Example: <code>/addadmin 123456789</code>"
                )
                return
            
            new_admin_id = int(parts[1])
            if new_admin_id not in self.admin_ids:
                self.admin_ids.append(new_admin_id)
                self.save_admin_ids(self.admin_ids)
                
                self.bot.reply_to(message,
                    f"✅ <b>New Admin Added!</b>\n\n"
                    f"• User ID: <code>{new_admin_id}</code>\n"
                    f"• Total Admins: <code>{len(self.admin_ids)}</code>"
                )
            else:
                self.bot.reply_to(message, "❌ User is already an admin.")
                
        except Exception as e:
            logger.error(f"❌ Error adding admin: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    def remove_admin(self, message):
        """Remove admin"""
        try:
            parts = message.text.split()
            if len(parts) < 2:
                # Show current admins
                admins_list = "👑 <b>Current Admins:</b>\n\n"
                for admin_id in self.admin_ids:
                    admins_list += f"• <code>{admin_id}</code>\n"
                
                admins_list += "\nTo remove: <code>/removeadmin user_id</code>"
                self.bot.reply_to(message, admins_list)
                return
            
            remove_admin_id = int(parts[1])
            if remove_admin_id in self.admin_ids:
                self.admin_ids.remove(remove_admin_id)
                self.save_admin_ids(self.admin_ids)
                
                self.bot.reply_to(message,
                    f"✅ <b>Admin Removed!</b>\n\n"
                    f"• User ID: <code>{remove_admin_id}</code>\n"
                    f"• Remaining Admins: <code>{len(self.admin_ids)}</code>"
                )
            else:
                self.bot.reply_to(message, "❌ User ID not found in admin list.")
                
        except Exception as e:
            logger.error(f"❌ Error removing admin: {e}")
            self.bot.reply_to(message, f"❌ Error: {str(e)}")
    
    # 🔄 CALLBACK QUERY HANDLER
    
    def handle_admin_callback(self, call):
        """Handle admin callback queries"""
        if not self.is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "❌ Access Denied!")
            return
        
        callback_data = call.data
        
        if callback_data == "admin_broadcast":
            self.start_broadcast(call.message)
        elif callback_data == "admin_stats":
            self.show_bot_stats(call.message)
        elif callback_data == "admin_users":
            self.manage_users(call.message)
        elif callback_data == "admin_force_sub":
            self.show_force_sub_settings(call.message)
        elif callback_data == "admin_welcome":
            self.show_welcome_settings(call.message)
        elif callback_data == "admin_manage":
            self.show_admin_management(call.message)
        
        self.bot.answer_callback_query(call.id)
    
    def show_force_sub_settings(self, message):
        """Show force subscription settings"""
        if not self.force_sub_channels:
            channels_text = "❌ No channels configured"
        else:
            channels_text = "🔗 <b>Current Channels:</b>\n"
            for channel_id, channel_data in self.force_sub_channels.items():
                channels_text += f"• {channel_data['username']} (<code>{channel_id}</code>)\n"
        
        settings_text = f"""
🔗 <b>FORCE SUBSCRIPTION SETTINGS</b>

{channels_text}

<b>Commands:</b>
<code>/forceadd channel_id @username</code> - Add channel
<code>/forceremove channel_id</code> - Remove channel
        """
        
        self.bot.send_message(message.chat.id, settings_text)
    
    def show_welcome_settings(self, message):
        """Show welcome message settings"""
        welcome_text = self.welcome_settings.get('welcome_text', 'Not set')
        has_image = "✅ Yes" if self.welcome_settings.get('image_url') else "❌ No"
        enabled = "✅ Enabled" if self.welcome_settings.get('enabled', True) else "❌ Disabled"
        
        settings_text = f"""
👋 <b>WELCOME MESSAGE SETTINGS</b>

<b>Status:</b> {enabled}
<b>Has Image:</b> {has_image}

<b>Current Message:</b>
<code>{welcome_text}</code>

<b>Command:</b>
<code>/setwelcome Your message here</code> - Update welcome message
        """
        
        self.bot.send_message(message.chat.id, settings_text)
    
    def show_admin_management(self, message):
        """Show admin management panel"""
        admins_text = "👑 <b>Current Admins:</b>\n"
        for admin_id in self.admin_ids:
            admins_text += f"• <code>{admin_id}</code>\n"
        
        management_text = f"""
👑 <b>ADMIN MANAGEMENT</b>

{admins_text}

<b>Commands:</b>
<code>/addadmin user_id</code> - Add new admin
<code>/removeadmin user_id</code> - Remove admin
        """
        
        self.bot.send_message(message.chat.id, management_text)
