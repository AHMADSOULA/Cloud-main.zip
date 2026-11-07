from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import config
from bot import handlers
from database.db import init_db
from utils.logger import get_logger
import traceback

log = get_logger("Main")

async def post_init(app):
    await init_db()
    from database import db
    await db.register_user(config.ADMIN_ID, "ADMIN")
    log.info("✅ DB ready")

async def error_handler(update, context):
    log.error(f"❌ خطأ: {context.error}")
    traceback.print_exc()
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="⚠️ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى."
            )
    except:
        pass

def main():
    log.info("🚀 starting...")
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.route_text))
    
    # ✅ باش البوت ما يطيحش إلا وقع خطأ
    app.add_error_handler(error_handler)
    
    app.run_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=True)

if __name__ == "__main__":
    main()
