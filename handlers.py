import asyncio
import io
import base64
import json
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot import messages
from bot.keyboards import main_menu
from database import db
from utils.helpers import extract_urls
from utils.logger import get_logger
from config import config
from automation.browser import StealthBrowser
from automation.sso_flow import run_sso_flow

log = get_logger("Handlers")

# ═══════════════════════════════════════════
# طابور
# ═══════════════════════════════════════════

class JobQueue:
    def __init__(self):
        self.queue = []
        self.counter = 0
        self.current = None
        self.lock = asyncio.Lock()

    async def add(self, user_id, chat_id, sso_url, user_tag):
        async with self.lock:
            self.counter += 1
            num = self.counter
            self.queue.append({
                "num": num,
                "user_id": user_id,
                "chat_id": chat_id,
                "sso_url": sso_url,
                "user_tag": user_tag,
            })
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


queue = JobQueue()


# ═══════════════════════════════════════════
# 3 ملفات DarkTunnel
# ═══════════════════════════════════════════

DARK_FILES = [
    {
        "name": "YOUTUBE_4H_🇺🇸",
        "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiWVVPVFVCRV80SF_wn4e68J-HuCIsInZsZXNzVHVubmVsQ29uZmlnIjp7InYycmF5Q29uZmlnIjp7Imhvc3QiOiJnb29nbGUuY29tIiwicG9ydCI6NDQzLCJ1dWlkIjoiYWFhYTExMTEtYmJiYi00Y2NjLThkZGQtZWVlZWZmZmYwMDAwIiwic2VydmVyTmFtZUluZGljYXRpb24iOiJnb29nbGV2aWRlby5jb20iLCJ3c1BhdGgiOiIvVGVsZWdyYW0vQEFNMl9EMy9AQUhNQUQzMjE0Iiwid3NIZWFkZXJIb3N0IjoiYWhtZWQtdmlwMS0xMDI3OTc3MDQ3ODgudXMtY2VudHJhbDEucnVuLmFwcCJ9LCJpbmplY3RDb25maWciOnsibW9kZSI6IlBST1hZIiwicHJveHlIb3N0IjoiMTU3LjI0MC45LjM5IiwicGF5bG9hZCI6IkNPTk5FQ1QgW2hvc3RdOltwb3J0XSBIVFRQLzEuMVtjcmxmXXgtY29ubmVjdGVkLXRvOiAzNC4xNDMuNzIuMltjcmxmXXByb3h5LWNvbm5lY3Rpb246IGtlZXAtYWxpdmVbY3JsZl1jb25uZWN0aW9uOiBrZWVwLWFsaXZlW2NybGZddXNlci1hZ2VudDogRkJBVi8wLjAgW2NybGZdeC1pb3JnLWJzaWQ6IEBBTTJfRDNbY3JsZl1bY3JsZl0ifX19",
    },
    {
        "name": "SNAPCHAT_4H_🇺🇸",
        "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiU05BUENIQVRfNEhf8J-HuvCfh7giLCJ2bGVzc1R1bm5lbENvbmZpZyI6eyJ2MnJheUNvbmZpZyI6eyJob3N0IjoiZ29vZ2xlLmNvbSIsInBvcnQiOjQ0MywidXVpZCI6ImFhYWExMTExLWJiYmItNGNjYy04ZGRkLWVlZWVmZmZmMDAwMCIsInNlcnZlck5hbWVJbmRpY2F0aW9uIjoiYXBpLnNuYXBjaGF0LmNvbSIsIndzUGF0aCI6Ii9UZWxlZ3JhbS9AQU0yX0QzL0BBSE1BRDMyMTQiLCJ3c0hlYWRlckhvc3QiOiJhaG1lZC12aXAxLTEwMjc5NzcwNDc4OC51cy1jZW50cmFsMS5ydW4uYXBwIn0sImluamVjdENvbmZpZyI6eyJtb2RlIjoiUFJPWFkiLCJwcm94eUhvc3QiOiIxNTcuMjQwLjkuMzkiLCJwYXlsb2FkIjoiQ09OTkVDVCBbaG9zdF06W3BvcnRdIEhUVFAvMS4xW2NybGZdeC1jb25uZWN0ZWQtdG86IDM0LjE0My43Mi4yW2NybGZdcHJveHktY29ubmVjdGlvbjoga2VlcC1hbGl2ZVtjcmxmXWNvbm5lY3Rpb246IGtlZXAtYWxpdmVbY3JsZl11c2VyLWFnZW50OiBGQkFWLzAuMCBbY3JsZl14LWlvcmctYnNpZDogQEFNMl9EM1tjcmxmXVtjcmxmXSJ9fX0=",
    },
    {
        "name": "FREE_4H_🇺🇸",
        "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiRlJFRV80SF_wn4e68J-HuCIsInZsZXNzVHVubmVsQ29uZmlnIjp7InYycmF5Q29uZmlnIjp7Imhvc3QiOiJhbHQxMy55dDMuZ2dwaHQuY29tIiwicG9ydCI6NDQzLCJ1dWlkIjoiYWFhYTExMTEtYmJiYi00Y2NjLThkZGQtZWVlZWZmZmYwMDAwIiwic2VydmVyTmFtZUluZGljYXRpb24iOiJhbHQxMy55dDMuZ2dwaHQuY29tIiwid3NQYXRoIjoiL1RlbGVncmFtL0BBTTJfRDMvQEFITUFEMzIxNCIsIndzSGVhZGVySG9zdCI6ImFobWVkLXZpcDEtMTAyNzk3NzA0Nzg4LnVzLWNlbnRyYWwxLnJ1bi5hcHAifSwiaW5qZWN0Q29uZmlnIjp7ImVuYWJsZWQiOnRydWUsIm1vZGUiOiJQUk9YWSIsInByb3h5SG9zdCI6IjE1Ny4yNDAuOS4zOSIsInBheWxvYWQiOiJDT05ORUNUIFtob3N0XTpbcG9ydF0gSFRUUC8xLjFbY3JsZl14LWNvbm5lY3RlZC10bzogMzQuMTQzLjcyLjJbY3JsZl1wcm94eS1jb25uZWN0aW9uOiBrZWVwLWFsaXZlW2NybGZdY29ubmVjdGlvbjoga2VlcC1hbGl2ZVtjcmxmXXVzZXItYWdlbnQ6IEZCQVYvMC4wIFtjcmxmXXgtaW9yZy1ic2lkOiBAQU0yX0QzW2NybGZdW2NybGZdIn19fQ==",
    },
]


def _b64_pad(s: str) -> str:
    return s + ("=" * ((4 - (len(s) % 4)) % 4)) if s else s


def build_darktunnel_uri_with_host(base_uri: str, new_host: str) -> str:
    b64 = _b64_pad(base_uri.split("darktunnel://", 1)[1].strip())
    data = json.loads(base64.b64decode(b64.encode("utf-8")).decode("utf-8"))

    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "wsHeaderHost" in cur:
                cur["wsHeaderHost"] = new_host
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(v for v in cur if isinstance(v, (dict, list)))

    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "darktunnel://" + base64.b64encode(raw).decode("utf-8")


# ═══════════════════════════════════════════
# الأوامر
# ═══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.register_user(user.id, user.username or user.first_name)
    await update.message.reply_text(
        messages.WELCOME, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(messages.WELCOME, parse_mode=ParseMode.MARKDOWN)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    jobs = await db.get_user_jobs(user.id, limit=5)
    if not jobs:
        await update.message.reply_text("📭 لا توجد مهام سابقة.")
        return
    lines = []
    for jid, status, created in jobs:
        emoji = {"pending": "⏳", "done": "✅", "failed": "❌", "running": "🔄"}.get(status, "❔")
        lines.append(f"• `#{jid}` — {emoji} {status} — {created}")
    await update.message.reply_text(
        f"📊 *آخر {len(jobs)} مهام:*\n\n" + "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.clear_session(user.id)
    b = context.bot_data.pop(f"browser_{user.id}", None)
    if b:
        try:
            await b.close()
        except Exception:
            pass
    await update.message.reply_text("🚫 تم الإلغاء.")


# ═══════════════════════════════════════════
# استقبال SSO — صامت (بلا رسائل)
# ═══════════════════════════════════════════

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text(messages.NO_URL)
        return
    sso_url = urls[0]
    user = update.effective_user

    if "skills.google" not in sso_url and "qwiklabs" not in sso_url:
        await update.message.reply_text("⚠️ الرابط لا يبدو من Google Skills.")
        return

    user_tag = f"@{user.username}" if user.username else f"@{user.first_name}"

    num = await queue.add(user.id, update.effective_chat.id, sso_url, user_tag)

    # ✅ رسالة وحدة فقط
    await update.message.reply_text(
        f"📥 تم استلام الرابط رقم {num} وسيبدأ الآن.\n"
        f"يمكنك إرسال رابط آخر وسيضاف إلى الطابور تلقائياً."
    )

    asyncio.create_task(process_queue(update.effective_chat.id, user.id, context))


# ═══════════════════════════════════════════
# معالجة الطابور — صامت
# ═══════════════════════════════════════════

async def process_queue(chat_id, user_id, context):
    async with asyncio.Lock():
        item = await queue.get_next()
        if not item:
            return

        job = item
        try:
            browser = StealthBrowser()
            ctx = await browser.start()

            try:
                result = await run_sso_flow(
                    ctx,
                    job["sso_url"],
                    image=config.DEFAULT_IMAGE,
                    sender=None,  # صامت
                    user_tag=job["user_tag"],
                )

                domain = result["domain"]
                final_url = result["final_url"]

                # ✅ رسالة واحدة في الأخير
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ **𝙃𝙚𝙧𝙚 𝙮𝙤𝙪 𝙜𝙤 𝙗𝙧𝙤**\n\n"
                        f"🌐 **Domain:**\n`{domain}`\n\n"
                        f"🔗 **URL:**\n`{final_url}`"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )

                # ✅ 3 ملفات darktunnel
                for dark in DARK_FILES:
                    try:
                        new_uri = build_darktunnel_uri_with_host(dark["uri"], domain)

                        safe_domain = "".join(
                            c for c in domain.lower()
                            if c.isalnum() or c in ".-_"
                        )[:40]

                        filename = f"{dark['name']} - {safe_domain}.dark"

                        bio = io.BytesIO(new_uri.encode("utf-8"))
                        bio.name = filename

                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=bio,
                            filename=filename,
                            caption=f"✅ {dark['name']}\n`{domain}`",
                        )
                    except Exception as e:
                        log.warning(f"⚠️ dark {dark['name']}: {e}")

            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

        except Exception as e:
            log.exception("فشل تنفيذ المهمة")
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ فشل\n\n{str(e)[:400]}")
            except Exception:
                pass

        finally:
            await queue.finish()

            if queue.queue_size() > 0:
                asyncio.create_task(process_queue(chat_id, user_id, context))


# ═══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "status":
        await status_cmd(update, context)
    elif query.data == "help":
        await query.message.reply_text(messages.WELCOME, parse_mode=ParseMode.MARKDOWN)
