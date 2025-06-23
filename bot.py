import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus

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
            await asyncio.sleep(300)  # 5 דקות
            self.load_blocked_keywords()
    
    async def is_admin(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
        """בדיקה אם המשתמש הוא מנהל בקבוצה"""
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בהודעות"""
        if not update.message or not update.message.chat:
            return
        
        chat = update.message.chat
        message = update.message
        
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
                                
                                # שליחת הודעה למנהלים (אופציונלי)
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
                        
                        break  # יציאה מהלולאה אחרי מציאת המילה הראשונה
                        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בשגיאות"""
        logger.error(f"Exception while handling an update: {context.error}")
    
    def run(self):
        """הפעלת הבוט"""
        # טעינת מילות מפתח
        self.load_blocked_keywords()
        
        # יצירת האפליקציה
        application = Application.builder().token(self.bot_token).build()
        
        # הוספת handlers
        application.add_handler(MessageHandler(filters.ALL, self.handle_message))
        application.add_error_handler(self.error_handler)
        
        # הפעלת טעינה מחדש תקופתית
        asyncio.create_task(self.reload_keywords_periodically())
        
        # הפעלת הבוט
        port = int(os.getenv('PORT', 8000))
        logger.info(f"Starting bot on port {port}")
        
        # הפעלה עם webhook ל-Render
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=self.bot_token,
            webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_URL', 'your-app-name.onrender.com')}/{self.bot_token}"
        )

if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()