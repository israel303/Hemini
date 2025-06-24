import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden
import aiohttp
from aiohttp import web

# הגדרת לוגים
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.blocked_keywords = set()
        self.keywords_file = 'blocked_keywords.txt'
        self.last_activity = datetime.now()
        
        if not self.bot_token:
            raise ValueError("BOT_TOKEN environment variable is required")
    
    def load_blocked_keywords(self):
        """טעינת מילות מפתח חסומות מהקובץ"""
        try:
            if os.path.exists(self.keywords_file):
                with open(self.keywords_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.blocked_keywords = {
                        keyword.strip().lower() 
                        for keyword in content.splitlines() 
                        if keyword.strip() and not keyword.strip().startswith('#')
                    }
                logger.info(f"Loaded {len(self.blocked_keywords)} blocked keywords")
            else:
                logger.warning(f"Keywords file {self.keywords_file} not found")
        except Exception as e:
            logger.error(f"Error loading blocked keywords: {e}")
    
    async def reload_keywords_periodically(self):
        """טעינה מחדש של מילות המפתח כל 5 דקות"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 דקות
                self.load_blocked_keywords()
                self.last_activity = datetime.now()
                logger.info("Reloaded keywords - keeping alive")
            except Exception as e:
                logger.error(f"Error in periodic reload: {e}")
    
    async def keep_alive_task(self):
        """משימה לשמירה על הבוט פעיל"""
        app_name = os.getenv('RENDER_SERVICE_NAME', 'your-app-name')
        ping_url = f"https://{app_name}.onrender.com/health"
        
        while True:
            try:
                await asyncio.sleep(600)  # 10 דקות
                
                # שליחת בקשת ping לעצמנו
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(ping_url, timeout=30) as response:
                            if response.status == 200:
                                logger.info(f"Keep-alive ping successful: {response.status}")
                            else:
                                logger.warning(f"Keep-alive ping returned: {response.status}")
                    except Exception as e:
                        logger.warning(f"Keep-alive ping failed: {e}")
                
                self.last_activity = datetime.now()
                
            except Exception as e:
                logger.error(f"Error in keep-alive task: {e}")
    
    async def health_check(self, request):
        """endpoint לבדיקת בריאות השירות"""
        uptime = datetime.now() - self.last_activity
        return web.json_response({
            'status': 'healthy',
            'uptime_minutes': int(uptime.total_seconds() / 60),
            'last_activity': self.last_activity.isoformat(),
            'blocked_keywords_count': len(self.blocked_keywords)
        })
    
    async def set_webhook(self, application):  # שינוי: הוספת פונקציה להגדרת Webhook
        """הגדרת Webhook עם בדיקה"""
        webhook_url = f"https://{os.getenv('RENDER_SERVICE_NAME', 'your-app-name')}.onrender.com/{self.bot_token}"
        current_webhook = await application.bot.get_webhook_info()
        if current_webhook.url != webhook_url:
            await application.bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
        else:
            logger.info(f"Webhook already set to: {webhook_url}")
    
    async def shutdown(self, application):  # שינוי: הוספת פונקציה לסגירה
        """מחיקת Webhook בסגירה"""
        await application.bot.delete_webhook()
        logger.info("Webhook deleted on shutdown")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת התחלה - לבדיקה שהבוט עובד"""
        self.last_activity = datetime.now()
        
        if update.message.chat.type in ['group', 'supergroup']:  # תיקון: תיקון שגיאת כתיב
            await update.message.reply_text(
                "🤖 הבוט פעיל ועובד!\n\n"
                "פקודות זמינות:\n"
                "• /cleanup - ניקוי הודעות הצטרפות ישנות (למנהלים בלבד)\n\n"
                "הבוט מוחק אוטומטית:\n"
                "• הודעות הצטרפות וניתוק\n"
                "• הודעות עם מילות מפתח חסומות"
            ")
        else:
            await update.message.reply_text("הבוט עובד רק בקבוצות!")
    
    async def is_admin(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
        """בדיקה אם המשתמש הוא מנהל בקבוצה"""
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            logger.info(f"User {user_id} status in chat {chat_id}: {member.status}")
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            logger.info(f"User {user_id} is admin: {is_admin}")
            return is_admin
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
            return False
    
    async def cleanup_old_join_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מחיקת הודעות הצטרפות ישנות (פקודה למנהלים בלבד)"""
        self.last_activity = datetime.now()
        
        if not update.message or not update.message.chat:
            return
        
        chat = update.message.chat
        user = update.message.from_user
        
        logger.info(f"Cleanup command received from user {user.id} ({user.username or user.first_name}) in chat {chat.id}")
        
        # בדיקה שהפקודה מופעלת בקבוצה
        if chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("הפקודה הזו עובדת רק בקבוצות")
            return
        
        # בדיקה שהבוט הוא מנהל
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if not bot_member.can_delete_messages:
            await update.message.reply_text("הבוט צריך הרשאות מחיקת הודעות")
            return
        
        status_message = await update.message.reply_text(
            "🔍 מחפש הודעות הצטרפות ישנות...\n"
            "⚠️ אני אמחק רק הודעות הצטרפות ויציאה"
        )
        
        deleted_join_messages = 0
        deleted_leave_messages = 0
        checked_messages = 0
        errors = 0
        current_message_id = update.message.message_id
        
        try:
            # חיפוש לאחור מההודעה הנוכחית
            for message_id in range(current_message_id - 1, max(1, current_message_id - 1000), -1):
                try:
                    checked_messages += 1
                    
                    # ננסה לקבל מידע על ההודעה באמצעות forward
                    try:
                        message_info = await context.bot.forward_message(
                            chat_id=chat.id,
                            from_chat_id=chat.id,
                            message_id=message_id,
                            disable_notification=True
                        )
                        
                        # אם ההודעה הועברה בהצלחה, נמחק את ההעברה מיד
                        await context.bot.delete_message(chat.id, message_info.message_id)
                        continue
                        
                    except BadRequest as forward_error:
                        # אם לא ניתן להעביר, זו עשויה להיות הודעת מערכת
                        if "can't be forwarded" in str(forward_error).lower() or "message can't be forwarded" in str(forward_error).lower():
                            try:
                                await context.bot.delete_message(chat.id, message_id)
                                deleted_join_messages += 1
                                logger.info(f"Deleted system message (likely join/leave) at message_id {message_id}")
                                
                                # עדכון סטטוס כל 5 מחיקות
                                if (deleted_join_messages + deleted_leave_messages) % 5 == 0:
                                    await status_message.edit_text(
                                        f"🗑️ נמחקו עד כה:\n"
                                        f"📥 הודעות הצטרפות: {deleted_join_messages}\n"
                                        f"📤 הודעות יציאה: {deleted_leave_messages}\n"
                                        f"🔍 נבדקו: {checked_messages} הודעות"
                                    )
                                    await asyncio.sleep(0.3)
                                
                            except BadRequest as delete_error:
                                if "Message to delete not found" in str(delete_error):
                                    continue
                                elif "Message can't be deleted" in str(delete_error):
                                    continue
                                else:
                                    logger.warning(f"Could not delete message {message_id}: {delete_error}")
                        else:
                            continue
                
                except Exception as e:
                    errors += 1
                    if errors > 50:
                        logger.error(f"Too many errors during cleanup: {e}")
                        break
                    continue
                
                # השהיה קלה למניעת rate limiting
                if checked_messages % 50 == 0:
                    await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            await status_message.edit_text(f"❌ שגיאה במהלך הניקוי: {str(e)}")
            return
        
        # הודעת סיכום
        total_deleted = deleted_join_messages + deleted_leave_messages
        summary = f"✅ סיימתי לנקות!\n\n"
        summary += f"🗑️ נמחקו בסך הכל: {total_deleted} הודעות מערכת\n"
        summary += f"📥 הודעות הצטרפות/יציאה: {deleted_join_messages}\n"
        summary += f"🔍 נבדקו: {checked_messages} הודעות\n"
        
        if errors > 0:
            summary += f"⚠️ שגיאות: {errors}\n"
        
        if total_deleted == 0:
            summary += "\n💡 לא נמצאו הודעות הצטרפות ישנות למחיקה"
        else:
            summary += f"\n💡 מחקתי רק הודעות מערכת (הצטרפות/יציאה)"
        
        await status_message.edit_text(summary)
        
        # מחיקת הודעת הסיכום לאחר 30 שניות
        await asyncio.sleep(30)
        try:
            await status_message.delete()
            await update.message.delete()
        except:
            pass
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בהודעות"""
        self.last_activity = datetime.now()
        
        if not update.message or not update.message.chat:
            return
        
        chat = update.message.chat
        message = update.message
        
        # לוג לבדיקה
        if message.text and message.text.startswith('/'):
            logger.info(f"Command received: {message.text} from user {message.from_user.id} in chat {chat.id}")
        
        # עבודה רק על קבוצות וקבוצות-על
        if chat.type not in ['group', 'supergroup']:
            return
        
        try:
            # מחיקת הודעות הצטרפות
            if message.new_chat_members:
                logger.info(f"Deleting join message in chat {chat.id}")
                await message.delete()
                return
            
            # מחיקת הודעות יציאה
            if message.left_chat_member:
                logger.info(f"Deleting leave message in chat {chat.id}")
                await message.delete()
                return
            
            # בדיקת מילות מפתח חסומות
            if message.text:
                message_text = message.text.lower()
                
                # בדיקה אם ההודעה מכילה מילות מפתח חסומות
                for keyword in self.blocked_keywords:
                    if keyword in message_text:
                        logger.info(f"Found blocked keyword '{keyword}' in message from user {message.from_user.id}")
                        
                        # מחיקת ההודעה
                        await message.delete()
                        
                        # בדיקה אם הבוט יכול לחסום משתמשים
                        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                        if bot_member.can_restrict_members:
                            try:
                                # חסימת המשתמש
                                await context.bot.ban_chat_member(
                                    chat_id=chat.id,
                                    user_id=message.from_user.id
                                )
                                logger.info(f"Banned user {message.from_user.id} for using blocked keyword")
                                
                                # שליחת הודעה למנהלים
                                username = message.from_user.username or message.from_user.first_name
                                notification_msg = await context.bot.send_message(
                                    chat_id=chat.id,
                                    text=f"🚫 המשתמש {username} נחסם בגלל שימוש במילה חסומה",
                                    disable_notification=True
                                )
                                
                                # מחיקת הודעת ההתראה לאחר 10 שניות
                                await asyncio.sleep(10)
                                try:
                                    await context.bot.delete_message(
                                        chat_id=chat.id,
                                        message_id=notification_msg.message_id
                                    )
                                except:
                                    pass
                                    
                            except Exception as e:
                                logger.error(f"Error banning user: {e}")
                        else:
                            logger.warning("Bot doesn't have permission to ban users")
                        
                        break
                        
        except Exception as e:
            logger.error(f"Error handling message: { {e}")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בשגיאות"""
        logger.error(f"Exception while handling an update: {context.error}")
    
    def run(self):
        """הפעלת הבוט"""
        # טעינת מילות מפתח
        self.load_blocked_keywords()
        self.last_activity = datetime.now()
        
        # יצירת האפליקציה
        application = Application.builder().token(self.bot_token).build()
        
        # הוספת handlers
        application.add_handler(CommandHandler("cleanup", self.cleanup_old_join_messages))
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        application.add_error_handler(self.error_handler)
        
        # הפעלת משימות רקע
        asyncio.create_task(self.reload_keywords_periodically())
        asyncio.create_task(self.keep_alive_task())
        
        # הגדרת web server עם health check
        app = web.Application()
        app.router.add_get('/health', self.health_check)
        
        # הפעלת הבוט
        port = int(os.getenv('PORT', 8443))  # שינוי: ברירת מחדל לפורט 8443
        logger.info(f"Starting bot on port {port}")
        
        app_name = os.getenv('RENDER_SERVICE_NAME', 'your-app-name')
        webhook_url = f"https://{{app_name}}.onrender.com/{self.bot_token}"
        
        logger.info(f"Setting webhook URL: {webhook_url}")
        logger.info("Starting background tasks for keep-alive and keyword reloading")
        
        # שינוי: הגדרת Webhook לפני הפעלה
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.set_webhook(application))
        
        try:
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=f"/{self.bot_token}",
                webhook_url=webhook_url
            )
        finally:
            # שינוי: מחיקת Webhook בסגירה
            loop.run_until_complete(self.shutdown(application))

if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()