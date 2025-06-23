import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# הגדרות לוגינג
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# קובץ עם תווים ואמוג'י חסומים
BANNED_CHARS_FILE = 'banned_chars.txt'
BANNED_CHARS = set()

def load_banned_chars():
    """טוען תווים ואמוג'י חסומים מקובץ."""
    try:
        with open(BANNED_CHARS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                char = line.strip()
                if char:
                    BANNED_CHARS.add(char)
        logger.info(f"Loaded {len(BANNED_CHARS)} banned characters from {BANNED_CHARS_FILE}")
    except FileNotFoundError:
        logger.warning(f"Banned characters file '{BANNED_CHARS_FILE}' not found. No characters will be banned based on this file.")
    except Exception as e:
        logger.error(f"Error loading banned characters: {e}")

async def delete_join_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מוחק הודעות הצטרפות לקבוצה."""
    if update.message.new_chat_members:
        try:
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
            logger.info(f"Deleted join message in chat {update.message.chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete join message in chat {update.message.chat_id}: {e}")

async def handle_message_for_banning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """בודק הודעות לתווים ואמוג'י חסומים ומוחק/חוסם משתמשים."""
    if update.message and update.message.text:
        text = update.message.text
        user = update.message.from_user
        chat_id = update.message.chat_id

        # בדיקה אם ההודעה מכילה תווים חסומים או את אימוג'י 🇵🇸
        is_banned = False
        reason = ""
        
        # בדיקה עבור אמוג'י 🇵🇸
        if '🇵🇸' in text:
            is_banned = True
            reason = "Palestinian flag emoji"
        
        # בדיקה עבור תווים ערביים ותווים חסומים מהקובץ
        if not is_banned: # רק אם עדיין לא נחסם בגלל האמוג'י
            for char_code in range(0x0600, 0x06FF + 1):  # Unicode range for Arabic characters
                if chr(char_code) in text:
                    is_banned = True
                    reason = "Arabic characters"
                    break
            
            if not is_banned: # רק אם עדיין לא נחסם בגלל תווים ערביים
                for banned_char in BANNED_CHARS:
                    if banned_char in text:
                        is_banned = True
                        reason = f"Banned character: '{banned_char}'"
                        break

        if is_banned:
            try:
                # נסה למחוק את ההודעה
                await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
                logger.info(f"Deleted message from user {user.id} ({user.username}) in chat {chat_id} due to {reason}.")
                
                # נסה לחסום את המשתמש
                # הבוט חייב להיות אדמין עם הרשאת Block Users
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                logger.info(f"Banned user {user.id} ({user.username}) from chat {chat_id} due to {reason}.")
                
            except Exception as e:
                logger.error(f"Failed to delete message or ban user {user.id} ({user.username}) in chat {chat_id} for {reason}: {e}")

def main() -> None:
    """הפונקציה הראשית שמפעילה את הבוט."""
    # טען תווים חסומים בהפעלה
    load_banned_chars()

    # קבל את טוקן הבוט ממשתנה הסביבה
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        exit(1)

    application = Application.builder().token(token).build()

    # הוסף handler למחיקת הודעות הצטרפות
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, delete_join_messages))

    # הוסף handler לבדיקת הודעות לתווים חסומים ולחסימת משתמשים
    # חשוב: ודא שהבוט הוא אדמין בקבוצה עם הרשאות מחיקת הודעות וחסימת משתמשים.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_for_banning))

    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

