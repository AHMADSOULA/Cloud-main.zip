import hmac
import os

from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)

from config import config
from bot import handlers
from database.db import init_db
from utils.helpers import extract_urls
from utils.logger import get_logger

log = get_logger("Main")


async def post_init(app):
    await init_db()
    from database import db
    await db.register_user(config.ADMIN_ID, "ADMIN")


async def route_text(update, context):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    if await handlers.handle_admin_input(update, context, text):
        return
    if extract_urls(text):
        await handlers.handle_url(update, context)
        return
    await update.message.reply_text("ℹ️ أرسل /start للبدء.")


async def health(_request):
    return web.json_response({"status": "ok", "service": "cloud-run-telegram-bot"})


def build_application():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("status", handlers.status_cmd))
    app.add_handler(CommandHandler("cancel", handlers.cancel_cmd))
    app.add_handler(CommandHandler("request", handlers.request_cmd))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))
    return app


async def telegram_webhook(request):
    secret = config.WEBHOOK_SECRET
    if secret:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied, secret):
            raise web.HTTPForbidden(text="Invalid webhook secret")

    application = request.app["telegram_application"]
    payload = await request.json()
    update = Update.de_json(payload, application.bot)
    await application.process_update(update)
    return web.Response(text="ok")


async def on_startup(app):
    application = app["telegram_application"]
    await application.initialize()
    await post_init(application)

    if config.WEBHOOK_URL:
        webhook_url = config.WEBHOOK_URL.rstrip("/") + "/telegram"
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=config.WEBHOOK_SECRET or None,
            drop_pending_updates=True,
        )
        log.info("Telegram webhook configured: %s", webhook_url)
    else:
        log.warning("WEBHOOK_URL is empty; set it after the first Cloud Run deployment")

    await application.start()


async def on_cleanup(app):
    application = app["telegram_application"]
    await application.stop()
    await application.shutdown()


def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    web_app = web.Application(client_max_size=2 * 1024 * 1024)
    web_app["telegram_application"] = build_application()
    web_app.router.add_get("/", health)
    web_app.router.add_post("/telegram", telegram_webhook)
    web_app.on_startup.append(on_startup)
    web_app.on_cleanup.append(on_cleanup)

    web.run_app(
        web_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        access_log=None,
    )


if __name__ == "__main__":
    main()
