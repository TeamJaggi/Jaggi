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

def get_media_type(message):
    if not hasattr(message, 'media') or not message.media:
        return None
        
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.audio:
        return 'audio'
    elif message.sticker:
        return 'sticker'
    elif message.document:
        return 'document'
    elif message.voice:
        return 'voice'
    elif message.gif:
        return 'gif'
    else:
        return 'unknown'

def should_forward_media(message):
    if not hasattr(message, 'media') or not message.media:
        return True
        
    # Check specific media types
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
    
    # Debug info
    media_type = get_media_type(message)
    if media_type:
        print(f"Received {media_type} message in channel {chat_id}")
    
    # Check if this chat is a source channel
    if chat_id in bot.channel_pairs:
        # Check if this is a media message and if we should forward it
        if media_type and not should_forward_media(message):
            print(f"Skipping {media_type} due to settings")
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
                    if hasattr(message, 'media') and message.media:
                        # Forward media message with modified caption if needed
                        if message_text != original_text or message_text:
                            forwarded_msg = await client.send_file(
                                target_id,
                                file=message.media,
                                caption=message_text if message_text else None,
                                parse_mode='html' if message_text else None
                            )
                        else:
                            # Original media with original caption
                            forwarded_msg = await client.send_file(
                                target_id,
                                file=message.media,
                                caption=message.caption if message.caption else None
                            )
                    else:
                        # Forward text message with replacements
                        forwarded_msg = await client.send_message(target_id, message_text, parse_mode='html')
                    
                    # Save the message mapping for edit/delete sync
                    if forwarded_msg:
                        bot.save_message_mapping(message.id, chat_id, forwarded_msg.id, target_id)
                        print(f"Forwarded message {message.id} to channel {target_id}")
                    
                except Exception as e:
                    print(f"Error forwarding message to {target_id}: {e}")

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
                if hasattr(message, 'media') and message.media:
                    # For media messages, we can only edit the caption
                    if message_text != original_text and message_text:
                        await client.edit_message(target_id, target_msg_id, message_text, parse_mode='html')
                else:
                    # For text messages, edit the content
                    await client.edit_message(target_id, target_msg_id, message_text, parse_mode='html')
                print(f"Edited message {message.id} in channel {target_id}")
            except Exception as e:
                print(f"Error syncing edit: {e}")

@client.on(events.MessageDeleted)
async def handle_delete_message(event):
    if not bot.delete_sync or not bot.forwarding_enabled:
        return
        
    # Check if we have any mappings for deleted messages
    for deleted_msg_id in event.deleted_ids:
        for source_channel_id, messages in list(bot.message_mapping.items()):
            if deleted_msg_id in messages:
                # Delete all target messages
                target_mappings = messages[deleted_msg_id]
                for target_channel_id, target_message_id in list(target_mappings.items()):
                    try:
                        await client.delete_messages(target_channel_id, target_message_id)
                        print(f"Deleted message {target_message_id} from channel {target_channel_id}")
                    except Exception as e:
                        print(f"Error deleting message in {target_channel_id}: {e}")
                
                # Remove the mapping
                bot.delete_message_mapping(deleted_msg_id, source_channel_id)

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
    application.run_polling()

if __name__ == "__main__":
    # Start the client with the session string instead of prompting for input
    with client:
        print("✅ Client started with session string")
        
        # Run the main function
        main()