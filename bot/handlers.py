import asyncio
import io
import base64
import json
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot import messages
from bot.keyboards import main_menu, admin_menu
from database import db
from utils.helpers import extract_urls
from utils.logger import get_logger
from config import config
from automation.browser import StealthBrowser
from automation.sso_flow import run_sso_flow

log = get_logger("Handlers")

DARK_FILE_YOUTUBE = {
    "name": "YOUTUBE_4H", 
    "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiQEFNMl9EMyBZT1VUVUJFIiwidmxlc3NUdW5uZWxDb25maWciOnsidjJyYXlDb25maWciOnsiaG9zdCI6Imdvb2dsZS5jb20iLCJwb3J0Ijo0NDMsInV1aWQiOiJhYWFhMTExMS1iYmJiLTRjY2MtOGRkZC1lZWVlZmZmZjAwMDAiLCJzZXJ2ZXJOYW1lSW5kaWNhdGlvbiI6Imdvb2dsZXZpZGVvLmNvbSIsIndzUGF0aCI6Ii9UZWxlZ3JhbS9AQU0yX0QzL0BBSE1BRDMyMTQiLCJ3c0hlYWRlckhvc3QiOiJhaG1lZC12aXAxLTQ0NTg4MjYxNDUzNi51cy1jZW50cmFsMS5ydW4uYXBwIn19fQ=="
}

def _b64_pad(s: str) -> str:
    return s + ("=" * ((4 - (len(s) % 4)) % 4)) if s else s

def build_darktunnel_uri_with_host(base_uri: str, new_host: str) -> str:
    try:
        raw_b64 = _b64_pad(base_uri.split("darktunnel://", 1)[1].strip())
        data = json.loads(base64.b64decode(raw_b64.encode("utf-8")).decode("utf-8"))
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "wsHeaderHost" in cur: cur["wsHeaderHost"] = new_host
                stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
            elif isinstance(cur, list):
                stack.extend(v for v in cur if isinstance(v, (dict, list)))
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return "darktunnel://" + base64.b64encode(raw).decode("utf-8")
    except Exception as e:
        log.error(f"❌ build_darktunnel: {e}")
        return None

def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.register_user(user.id, user.username or user.first_name)
    if is_admin(user.id):
        await update.message.reply_text(messages.WELCOME_ADMIN, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin=True))
    else:
        await update.message.reply_text(messages.WELCOME_USER, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin=False))

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    urls = extract_urls(text)
    
    if not urls: return await update.message.reply_text("⚠️ أرسل رابط SSO صحيح.")
    sso_url = urls[0]

    # ✅ فحص الإيميل وكلمة السر
    if "addsession" in sso_url.lower() and "password=" not in sso_url.lower():
        await db.set_session(user.id, sso_url=sso_url, state="waiting_password")
        return await update.message.reply_text("📧 لقينا رابط الحساب.\n🔑 يرجى إرسال كلمة السر (Password) لإكمال العملية:")

    await process_deploy(update, context, sso_url)

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    password = (update.message.text or "").strip()
    if not password: return

    session = await db.get_session(user.id)
    if not session or session.get("state") != "waiting_password": return

    sso_url = session.get("sso_url")
    await db.clear_session(user.id)

    try: await update.message.delete() # نمسحو كلمة السر من الشات
    except: pass

    if "Password=" not in sso_url:
        sep = "&" if "?" in sso_url else "?"
        sso_url = f"{sso_url}{sep}Password={password}"

    await process_deploy(update, context, sso_url)

async def process_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE, sso_url: str):
    user = update.effective_user
    # ✅ رسالة وحدة كتتبدل
    status_msg = await update.message.reply_text("⏳ جاري التنفيذ... [0/6]")
    
    browser = StealthBrowser()
    try:
        ctx = await browser.start()
        result = await run_sso_flow(ctx, context.bot, update.effective_chat.id, sso_url, "docker.io/ajndjd2/ahmed-vip1", status_msg)
        
        # ✅ نمسحو الرسالة دايما ملي يكمل
        try: await status_msg.delete()
        except: pass

        if result.get("success"):
            domain = result.get("domain")
            # ✅ كيبعت غير الملف
            new_uri = build_darktunnel_uri_with_host(DARK_FILE_YOUTUBE["uri"], domain)
            if new_uri:
                bio = io.BytesIO(new_uri.encode("utf-8"))
                bio.name = f"{DARK_FILE_YOUTUBE['name']} - {domain}.dark"
                await context.bot.send_document(chat_id=update.effective_chat.id, document=bio, filename=bio.name)
        else:
            # ✅ عند الخطأ كيصيفط غير رسالة توقيف (والصورة تصيفطات من sso_flow)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ توقف الخدمة\nحدث مشكل أثناء التنفيذ.")
                
    except Exception as e:
        try: await status_msg.delete()
        except: pass
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ توقف الخدمة\nحدث خطأ غير متوقع.")
    finally:
        await browser.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_main":
        await query.message.edit_text(messages.WELCOME_USER, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin(query.from_user.id)))

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    
    # ✅ إلا كان المستخدم كيصيفط كلمة السر
    session = await db.get_session(user.id)
    if session and session.get("state") == "waiting_password":
        await handle_password(update, context)
        return

    if extract_urls(text):
        await handle_url(update, context)
        return
        
    await update.message.reply_text("ℹ️ أرسل رابط Qwiklabs SSO للبدء.")
