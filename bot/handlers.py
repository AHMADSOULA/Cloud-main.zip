import asyncio
import io
import os
import base64
import json
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot import messages
from bot.keyboards import main_menu, admin_menu
from database import db
from utils.helpers import extract_urls
from utils.logger import get_logger
from config import config
from automation.browser import StealthBrowser
from automation.sso_flow import run_sso_flow, extract_email_from_url

log = get_logger("Handlers")

# ═══════════════════════════════════════════
# طابور (priority-based)
# ═══════════════════════════════════════════
class JobQueue:
    def __init__(self):
        self.queue = []
        self.counter = 0
        self.current = None
        self.lock = asyncio.Lock()

    async def add(self, user_id, chat_id, sso_url, user_tag, priority=0):
        async with self.lock:
            self.counter += 1
            num = self.counter
            self.queue.append({
                "num": num,
                "user_id": user_id,
                "chat_id": chat_id,
                "sso_url": sso_url,
                "user_tag": user_tag,
                "priority": priority,
            })
            self.queue.sort(key=lambda x: -x["priority"])
            return num

    async def get_next(self):
        async with self.lock:
            if self.current is not None:
                return None
            if not self.queue:
                return None
            self.current = self.queue.pop(0)
            return self.current

    async def finish(self):
        async with self.lock:
            self.current = None

    def queue_size(self):
        return len(self.queue)

    def position(self, user_id):
        for i, item in enumerate(self.queue):
            if item["user_id"] == user_id:
                return i + 1
        return 0

queue = JobQueue()

def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID

# ═══════════════════════════════════════════
# فحص نوع الرابط
# ═══════════════════════════════════════════
def is_full_sso_url(url: str) -> bool:
    u = (url or "").lower()
    if "skills.google/google_sso" in u: return True
    if "token=" in u: return True
    if "password=" in u: return True
    return False

def is_direct_addsession_url(url: str) -> bool:
    u = (url or "").lower()
    if "accounts.google.com/addsession" in u and "skills.google" not in u: return True
    return False

# ═══════════════════════════════════════════
# handle_url
# ═══════════════════════════════════════════
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if await db.is_globally_stopped() and not is_admin(user.id):
        await update.message.reply_text("⛔ **البوت متوقف حالياً**\n\nجرب من بعد.", parse_mode=ParseMode.MARKDOWN)
        return

    if not await db.has_access(user.id):
        await update.message.reply_text("🔒 ما عندكش صلاحية.\nأرسل `/request` باش تطلب.", parse_mode=ParseMode.MARKDOWN)
        return

    text = update.message.text or ""
    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text(messages.NO_URL)
        return
    sso_url = urls[0]

    user_tag = f"@{user.username}" if user.username else f"@{user.first_name}"
    u = await db.get_user(user.id)
    priority = (u.get("priority") or 0) if u else 0

    # إذا كان رابط AddSession (يطلب كلمة سر)
    if is_direct_addsession_url(sso_url):
        email = extract_email_from_url(sso_url)
        if email:
            await db.set_session(user_id=user.id, sso_url=sso_url, state="waiting_password")
            await update.message.reply_text(
                f"🔐 **مطلوب كلمة السر**\n\n"
                f"📧 الإيميل:\n`{email}`\n\n"
                f"أرسل كلمة السر هنا.\n"
                f"⚠️ تجمد في مرحلة password لأكثر من 3 دقائق سيتم تخطي دورك.",
                parse_mode=ParseMode.MARKDOWN
            )
            # مؤقت 3 دقائق (180 ثانية) للتخطي
            asyncio.create_task(password_timeout(user.id, update.effective_chat.id, context))
            return
        else:
            await update.message.reply_text("⚠️ ما قدرناش نستخرجو الإيميل.")
            return

    # إذا كان رابط SSO كامل (Token موجود)
    if is_full_sso_url(sso_url):
        num = await queue.add(user.id, update.effective_chat.id, sso_url, user_tag, priority)
        pos = queue.position(user.id)
        msg = f"📥 تم استلام الرابط رقم {num}."
        if pos > 1: msg += f"\n📍 موقعك في الطابور: {pos}"
        await update.message.reply_text(msg)
        asyncio.create_task(process_queue(update.effective_chat.id, context))
        return

# ═══════════════════════════════════════════
# handle_password
# ═══════════════════════════════════════════
async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    password = (update.message.text or "").strip()
    if not password: return

    session = await db.get_session(user.id)
    if not session or session.get("state") != "waiting_password": return

    try: await update.message.delete()
    except: pass

    sso_url = session.get("sso_url")
    if not sso_url: return
    await db.clear_session(user.id)

    if "Password=" not in sso_url:
        sep = "&" if "?" in sso_url else "?"
        sso_url = f"{sso_url}{sep}Password={password}"

    user_tag = f"@{user.username}" if user.username else f"@{user.first_name}"
    u = await db.get_user(user.id)
    priority = (u.get("priority") or 0) if u else 0

    num = await queue.add(user.id, update.effective_chat.id, sso_url, user_tag, priority)
    pos = queue.position(user.id)
    
    msg = f"📥 تم استلام الرابط رقم {num}."
    if pos > 1: msg += f"\n📍 موقعك في الطابور: {pos}"
    await update.message.reply_text(msg)

    asyncio.create_task(process_queue(update.effective_chat.id, context))

# ═══════════════════════════════════════════
# مؤقت كلمة السر
# ═══════════════════════════════════════════
async def password_timeout(user_id, chat_id, context):
    await asyncio.sleep(180) # 3 دقائق
    session = await db.get_session(user_id)
    if session and session.get("state") == "waiting_password":
        await db.clear_session(user_id)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏳ تجمد في password\n\n⏭️ تم تخطي دورك بسبب التجمد. يمكنك إرسال الرابط مجدداً."
            )
        except: pass

# ═══════════════════════════════════════════
# process_queue
# ═══════════════════════════════════════════
async def process_queue(chat_id, context):
    async with asyncio.Lock():
        item = await queue.get_next()
        if not item: return
        job = item

        try:
            status_msg = await context.bot.send_message(chat_id=job["chat_id"], text="✅ تم استلام الرابط. جاري التنفيذ الآن...")

            browser = StealthBrowser()
            ctx = await browser.start()

            try:
                # تشغيل SSO Flow (سيقوم بإرسال الخطوات 1 إلى 12 بنفسه)
                result = await run_sso_flow(
                    ctx,
                    job["sso_url"],
                    image=config.DEFAULT_IMAGE,
                    sender=status_msg,
                    user_tag=job["user_tag"],
                )

                if not result.get("success"):
                    error_msg = result.get("message", "فشل غير معروف")
                    try:
                        if "account_deleted" in error_msg or "منتهي" in error_msg:
                            await status_msg.edit_text(f"⏳ تجمد في unknown\n\n⏭️ تم تخطي دورك بسبب التجمد. يمكنك إرسال الرابط مجدداً.")
                        else:
                            await status_msg.edit_text(f"❌ توقفنا\n\n{error_msg}")
                    except: pass
                    return

                domain = result.get("domain")
                final_url = result.get("final_url")

                if domain:
                    # توليد رابط VLESS كما في الصورة
                    vless_link = f"vless://ffff6667-7777-4555-8aaa-5555a7777fff@{domain}:443?encryption=none&security=tls&sni=youtube.com&fp=chrome&type=ws&host={domain}&path=%2FTelegram%2F%40IJ77m%2F%40zxhv67#GCP-Xray"
                    
                    await status_msg.edit_text(
                        f"🔗 **الرابط:**\n`{final_url}`\n\n"
                        f"📝 **VLESS:**\n`{vless_link}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await status_msg.edit_text("❌ فشل: ما لقيناش domain")

            finally:
                try: await browser.close()
                except: pass

        except Exception as e:
            log.exception("فشل تنفيذ المهمة")
            try:
                await context.bot.send_message(chat_id=job["chat_id"], text=f"❌ فشل\n\n{str(e)[:400]}")
            except: pass

        finally:
            await queue.finish()
            if queue.queue_size() > 0:
                asyncio.create_task(process_queue(job["chat_id"], context))

# (باقي الأكواد الخاصة بـ /start و /admin كما هي في ملفك الأصلي...)
