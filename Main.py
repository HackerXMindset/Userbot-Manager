import logging
import asyncio
import difflib
from io import BytesIO
from PIL import Image
import imagehash
from telegram import Update, ChatMember
from telegram.ext import Application, MessageHandler, filters, ContextTypes, ChatMemberHandler
from telegram.error import TelegramError
import requests

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AdminImpersonationDetector:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.application = Application.builder().token(bot_token).build()
        
        # Store admin data: {chat_id: {admin_id: {'name': str, 'pfp_hash': str}}}
        self.admin_profiles = {}
        
        # Whitelist for trusted users: {chat_id: set(user_ids)}
        self.whitelisted_users = {}
        
        # Sensitivity settings
        self.name_similarity_threshold = 0.8
        self.pfp_similarity_threshold = 10  # Hamming distance for image hashes
        
    async def get_admin_profiles(self, chat_id):
        """Fetch and store current admin profiles"""
        try:
            administrators = await self.application.bot.get_chat_administrators(chat_id)
            admin_data = {}
            
            for admin in administrators:
                if admin.user.is_bot:
                    continue
                    
                user = admin.user
                profile_data = {
                    'name': user.full_name or user.first_name,
                    'username': user.username,
                    'pfp_hash': None
                }
                
                # Get profile photo hash
                if user.get_profile_photos:
                    try:
                        photos = await self.application.bot.get_user_profile_photos(user.id, limit=1)
                        if photos.photos:
                            photo = photos.photos[0][-1]  # Get highest resolution
                            file = await self.application.bot.get_file(photo.file_id)
                            
                            # Download and hash the image
                            response = requests.get(file.file_path)
                            img = Image.open(BytesIO(response.content))
                            profile_data['pfp_hash'] = str(imagehash.phash(img))
                    except Exception as e:
                        logger.warning(f"Could not get profile photo for {user.id}: {e}")
                
                admin_data[user.id] = profile_data
            
            self.admin_profiles[chat_id] = admin_data
            logger.info(f"Updated admin profiles for chat {chat_id}: {len(admin_data)} admins")
            
        except Exception as e:
            logger.error(f"Error fetching admin profiles for chat {chat_id}: {e}")
    
    def calculate_name_similarity(self, name1, name2):
        """Calculate similarity between two names"""
        if not name1 or not name2:
            return 0
        
        # Convert to lowercase and remove spaces for comparison
        clean_name1 = name1.lower().replace(" ", "")
        clean_name2 = name2.lower().replace(" ", "")
        
        # Use difflib for similarity calculation
        similarity = difflib.SequenceMatcher(None, clean_name1, clean_name2).ratio()
        return similarity
    
    def calculate_pfp_similarity(self, hash1, hash2):
        """Calculate similarity between two image hashes"""
        if not hash1 or not hash2:
            return float('inf')
        
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return h1 - h2  # Hamming distance
        except:
            return float('inf')
    
    async def check_impersonation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if a user might be impersonating an admin"""
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        # Skip if user is a bot, an admin, or whitelisted
        if (user.is_bot or 
            chat_id not in self.admin_profiles or 
            user.id in self.admin_profiles[chat_id] or
            user.id in self.whitelisted_users.get(chat_id, set())):
            return
        
        user_name = user.full_name or user.first_name
        user_pfp_hash = None
        
        # Get user's profile photo hash
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.photos:
                photo = photos.photos[0][-1]
                file = await context.bot.get_file(photo.file_id)
                response = requests.get(file.file_path)
                img = Image.open(BytesIO(response.content))
                user_pfp_hash = str(imagehash.phash(img))
        except Exception as e:
            logger.warning(f"Could not get profile photo for user {user.id}: {e}")
        
        # Check against all admins
        suspicious_matches = []
        
        for admin_id, admin_data in self.admin_profiles[chat_id].items():
            name_similarity = self.calculate_name_similarity(user_name, admin_data['name'])
            pfp_similarity = self.calculate_pfp_similarity(user_pfp_hash, admin_data['pfp_hash'])
            
            # Check if either name or pfp is suspiciously similar
            is_name_suspicious = name_similarity >= self.name_similarity_threshold
            is_pfp_suspicious = pfp_similarity <= self.pfp_similarity_threshold
            
            if is_name_suspicious or is_pfp_suspicious:
                suspicious_matches.append({
                    'admin_name': admin_data['name'],
                    'admin_username': admin_data.get('username', 'No username'),
                    'name_similarity': name_similarity,
                    'pfp_similarity': pfp_similarity,
                    'reasons': []
                })
                
                if is_name_suspicious:
                    suspicious_matches[-1]['reasons'].append(f"Similar name ({name_similarity:.2%})")
                if is_pfp_suspicious:
                    suspicious_matches[-1]['reasons'].append(f"Similar profile picture (distance: {pfp_similarity})")
        
        # If suspicious matches found, take action
        if suspicious_matches:
            await self.handle_impersonation_detection(update, context, suspicious_matches)
    
    async def handle_impersonation_detection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, matches):
        """Handle detected impersonation: ban user, delete messages, and send alert"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # First, try to ban the user
        ban_success = await self.ban_impersonator(chat_id, user.id, context)
        
        # Delete the current message
        delete_success = await self.delete_message(update, context)
        
        # Delete recent messages from this user (last 50 messages)
        deleted_count = await self.delete_user_recent_messages(chat_id, user.id, context)
        
        # Send alert message
        await self.send_action_alert(chat_id, user, matches, ban_success, delete_success, deleted_count, context)
    
    async def ban_impersonator(self, chat_id, user_id, context):
        """Ban the impersonating user"""
        try:
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                revoke_messages=True  # This deletes all messages from the user in the last 48 hours
            )
            logger.info(f"Successfully banned user {user_id} from chat {chat_id}")
            return True
        except TelegramError as e:
            logger.error(f"Failed to ban user {user_id}: {e}")
            return False
    
    async def delete_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete the current message"""
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to delete message: {e}")
            return False
    
    async def delete_user_recent_messages(self, chat_id, user_id, context, limit=50):
        """Delete recent messages from the user (additional cleanup)"""
        deleted_count = 0
        try:
            # This is a fallback in case revoke_messages doesn't work perfectly
            # Note: This requires storing message IDs, which we'll implement simply
            pass  # The ban with revoke_messages=True should handle this
        except Exception as e:
            logger.error(f"Error in additional message cleanup: {e}")
        
        return deleted_count
    
    async def send_action_alert(self, chat_id, user, matches, ban_success, delete_success, deleted_count, context):
        """Send an alert about the actions taken"""
        
        alert_message = f"🚨 **ADMIN IMPERSONATION DETECTED & HANDLED** 🚨\n\n"
        
        # User info
        alert_message += f"**Banned User:** {user.full_name or user.first_name}"
        if user.username:
            alert_message += f" (@{user.username})"
        alert_message += f"\n**User ID:** `{user.id}`\n\n"
        
        # What they were impersonating
        alert_message += "**Was impersonating:**\n"
        for match in matches:
            alert_message += f"• **{match['admin_name']}**"
            if match['admin_username'] != 'No username':
                alert_message += f" (@{match['admin_username']})"
            alert_message += f"\n  *{', '.join(match['reasons'])}*\n"
        
        # Actions taken
        alert_message += "\n**Actions taken:**\n"
        if ban_success:
            alert_message += "✅ User banned from group\n"
            alert_message += "✅ All user messages deleted (last 48h)\n"
        else:
            alert_message += "❌ Failed to ban user (insufficient permissions)\n"
        
        if delete_success:
            alert_message += "✅ Current message deleted\n"
        else:
            alert_message += "❌ Failed to delete current message\n"
        
        alert_message += f"\n🛡️ **Group protected from impersonation attempt**"
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=alert_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending action alert: {e}")
            # Fallback without markdown
            try:
                simple_alert = f"🚨 ADMIN IMPERSONATION DETECTED!\n\nBanned user: {user.full_name or user.first_name} (ID: {user.id})\nReason: Impersonating admin\nActions: User banned and messages deleted"
                await context.bot.send_message(chat_id=chat_id, text=simple_alert)
            except Exception as e2:
                logger.error(f"Error sending fallback alert: {e2}")
    
    async def handle_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new chat members"""
        for member in update.message.new_chat_members:
            if not member.is_bot:
                # Check impersonation for new members
                await self.check_impersonation(update, context)
    
    async def handle_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin status changes"""
        chat_id = update.effective_chat.id
        
        # Refresh admin profiles when admin status changes
        if update.chat_member.new_chat_member.status in ['administrator', 'creator']:
            await self.get_admin_profiles(chat_id)
        elif update.chat_member.old_chat_member.status in ['administrator', 'creator']:
            await self.get_admin_profiles(chat_id)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages and check for impersonation"""
        chat_id = update.effective_chat.id
        
        # Initialize admin profiles if not exists
        if chat_id not in self.admin_profiles:
            await self.get_admin_profiles(chat_id)
        
        # Check for impersonation
        await self.check_impersonation(update, context)
    
    async def whitelist_add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add user to whitelist (admin only)"""
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        try:
            user_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
            if user_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("Only admins can manage the whitelist.")
                return
        except:
            return
        
        # Get user ID from command args or replied message
        if context.args:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("Please provide a valid user ID: `/whitelist_add 123456789`")
                return
        elif update.message.reply_to_message:
            target_user_id = update.message.reply_to_message.from_user.id
        else:
            await update.message.reply_text("Reply to a user's message or provide user ID: `/whitelist_add 123456789`")
            return
        
        # Add to whitelist
        if chat_id not in self.whitelisted_users:
            self.whitelisted_users[chat_id] = set()
        
        self.whitelisted_users[chat_id].add(target_user_id)
        await update.message.reply_text(f"✅ User {target_user_id} added to whitelist.")
    
    async def whitelist_remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove user from whitelist (admin only)"""
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        try:
            user_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
            if user_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("Only admins can manage the whitelist.")
                return
        except:
            return
        
        # Get user ID from command args
        if not context.args:
            await update.message.reply_text("Please provide a user ID: `/whitelist_remove 123456789`")
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please provide a valid user ID: `/whitelist_remove 123456789`")
            return
        
        # Remove from whitelist
        if chat_id in self.whitelisted_users:
            self.whitelisted_users[chat_id].discard(target_user_id)
            await update.message.reply_text(f"✅ User {target_user_id} removed from whitelist.")
        else:
            await update.message.reply_text("No whitelist exists for this chat.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detector status and statistics"""
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        try:
            user_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
            if user_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("Only admins can view detector status.")
                return
        except:
            return
        
        admin_count = len(self.admin_profiles.get(chat_id, {}))
        whitelist_count = len(self.whitelisted_users.get(chat_id, set()))
        
        status_message = f"🛡️ **Admin Impersonation Detector Status**\n\n"
        status_message += f"**Monitored Admins:** {admin_count}\n"
        status_message += f"**Whitelisted Users:** {whitelist_count}\n"
        status_message += f"**Name Similarity Threshold:** {self.name_similarity_threshold:.0%}\n"
        status_message += f"**Image Similarity Threshold:** {self.pfp_similarity_threshold}\n\n"
        status_message += f"**Status:** 🟢 Active & Monitoring\n\n"
        status_message += f"**Commands:**\n"
        status_message += f"• `/refresh_admins` - Update admin profiles\n"
        status_message += f"• `/whitelist_add [user_id]` - Add trusted user\n"
        status_message += f"• `/whitelist_remove [user_id]` - Remove from whitelist\n"
        status_message += f"• `/detector_status` - Show this status"
        
    async def refresh_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manual command to refresh admin profiles"""
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        try:
            user_member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
            if user_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("Only admins can refresh admin profiles.")
                return
        except:
            return
        
        await self.get_admin_profiles(chat_id)
        await update.message.reply_text("✅ Admin profiles refreshed successfully!")
    
    def setup_handlers(self):
        """Setup all bot handlers"""
        # Message handler for impersonation detection
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # New member handler
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_member)
        )
        
        # Chat member update handler
        self.application.add_handler(ChatMemberHandler(self.handle_chat_member_update))
        
        # Command to refresh admin profiles and whitelist management
        from telegram.ext import CommandHandler
        self.application.add_handler(CommandHandler("refresh_admins", self.refresh_admin_command))
        self.application.add_handler(CommandHandler("whitelist_add", self.whitelist_add_command))
        self.application.add_handler(CommandHandler("whitelist_remove", self.whitelist_remove_command))
        self.application.add_handler(CommandHandler("detector_status", self.status_command))
    
    def run(self):
        """Start the bot"""
        self.setup_handlers()
        
        logger.info("Starting Admin Impersonation Detection Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# Main execution
if __name__ == "__main__":
    BOT_TOKEN = "8339675467:AAHfV8kgTlivjLyeKbijZ6MQJuKLME3dwds"
    
    detector = AdminImpersonationDetector(BOT_TOKEN)
    
    try:
        detector.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot encountered an error: {e}")
