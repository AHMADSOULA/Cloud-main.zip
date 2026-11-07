from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import config
from bot import handlers
from database.db import init_db
from utils.logger import get_logger
from utils.helpers import extract_urls

log = get_logger("Main")

async def post_init(app):
    await init_db()
    from database import db
    await db.register_user(config.ADMIN_ID, "ADMIN")

async def route_text(update, context):
    text = update.message.text or ""
    
    # ✅ معالجة ملف Ooredoo
    if update.message.document:
        if await handlers.process_ooredoo_file(update, context):
            return

    # ✅ معالجة تحويل SSH
    if await handlers.handle_ssh_conversion_input(update, context):
        return
        
    # ✅ معالجة أزرار الأدمن
    if await handlers.handle_admin_input(update, context, text):
        return

    # ✅ معالجة رابط SSO
    if extract_urls(text):
        await handlers.handle_url(update, context)
        return

    await update.message.reply_text("ℹ️ أرسل /start للبدء.")

def main():
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("status", handlers.status_cmd))
    app.add_handler(CommandHandler("cancel", handlers.cancel_cmd))
    app.add_handler(CommandHandler("request", handlers.request_cmd))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, route_text))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
