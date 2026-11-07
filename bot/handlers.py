import os
from telegram import Update
from telegram.ext import ContextTypes
from bot import messages
from bot.keyboards import main_menu, admin_menu
from database import db
from utils.helpers import extract_urls
from utils.logger import get_logger
from config import config
from automation.browser import StealthBrowser
from automation.sso_flow import run_sso_flow

log = get_logger("Handlers")


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.register_user(user.id, user.username or user.first_name)
    if is_admin(user.id):
        await update.message.reply_text(
            messages.WELCOME_ADMIN, parse_mode="Markdown",
            reply_markup=main_menu(is_admin=True), disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text("🔒 أرسل /request باش تطلب صلاحية.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ /start - /admin - /cancel")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 البوت شغال على Cloud Run.")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 تم الإلغاء.")


async def request_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ تم إرسال طلبك.")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    urls = extract_urls(update.message.text or "")
    if not urls:
        return

    msg = await update.message.reply_text("⏳ جاري التنفيذ...")
    browser = StealthBrowser()
    try:
        ctx = await browser.start()
        result = await run_sso_flow(
            ctx, urls[0], image=config.DEFAULT_IMAGE, sender=msg,
            user_tag=user.username or "user",
        )
        if not result.get("success"):
            shot = result.get("screenshot")
            if shot and os.path.exists(shot):
                with open(shot, "rb") as f:
                    await update.message.reply_photo(
                        photo=f, caption=result.get("message", "❌ فشل التنفيذ")
                    )
                os.remove(shot)
                await msg.delete()
            else:
                await msg.edit_text(f"❌ فشل: {result.get('message')}")
            return

        await msg.edit_text(
            "✅ تم إنشاء خدمة Cloud Run بنجاح\\n" + result.get("final_url", "")
        )
    except Exception as exc:
        log.exception("Cloud Run deployment flow failed")
        await msg.edit_text(f"❌ خطأ: {str(exc)[:300]}")
    finally:
        await browser.close()


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        await query.message.edit_text(
            messages.WELCOME_ADMIN, parse_mode="Markdown",
            reply_markup=main_menu(True),
        )
    elif data == "admin":
        await query.message.edit_text("⚙️ ADMIN PANEL", reply_markup=admin_menu())
    elif data == "admin_stats":
        await query.message.edit_text("📊 الإحصائيات مازال ما تبرمجتش.")
    elif data == "admin_users":
        await query.message.edit_text("👥 المستخدمين مازال ما تبرمجوش.")
    elif data == "admin_banned":
        await query.message.edit_text("🚫 المحظورين مازال ما تبرمجوش.")
    elif data == "admin_requests":
        await query.message.edit_text("📋 الطلبات مازال ما تبرمجتش.")
    elif data == "admin_priority":
        context.user_data["await"] = "priority"
        await query.message.edit_text("⚡ أرسل ID:")
    elif data == "admin_ban":
        context.user_data["await"] = "ban"
        await query.message.edit_text("🔨 أرسل ID:")
    elif data == "admin_grant":
        context.user_data["await"] = "grant"
        await query.message.edit_text("✅ أرسل ID:")
    elif data == "admin_broadcast":
        context.user_data["await"] = "broadcast"
        await query.message.edit_text("📢 أرسل الرسالة:")
    elif data == "admin_stop_all":
        await db.set_global_stop(True)
        await query.message.edit_text("⛔ إيقاف للجميع", reply_markup=admin_menu())
    elif data == "admin_start_all":
        await db.set_global_stop(False)
        await query.message.edit_text("▶️ تشغيل للجميع", reply_markup=admin_menu())


async def handle_admin_input(update, context, text):
    mode = context.user_data.get("await")
    if not mode or not is_admin(update.effective_user.id):
        return False
    context.user_data.pop("await", None)
    try:
        if mode == "grant":
            await db.set_access(int(text), 1)
            await update.message.reply_text(f"✅ تم تفعيل {text}")
        elif mode == "ban":
            await db.set_ban(int(text), 1)
            await update.message.reply_text(f"🚫 تم حظر {text}")
        elif mode == "priority":
            await db.set_priority(int(text), 100)
            await update.message.reply_text(f"⚡ تم زيادة {text}")
        elif mode == "broadcast":
            users = await db.get_all_users()
            sent = 0
            for user in users:
                try:
                    await context.bot.send_message(chat_id=user["user_id"], text=text)
                    sent += 1
                except Exception:
                    pass
            await update.message.reply_text(f"📢 تم الإرسال لـ {sent}")
    except Exception as exc:
        await update.message.reply_text(f"❌ خطأ: {exc}")
    return True
