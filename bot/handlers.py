import asyncio
import io
import base64
import json
import os
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
from automation.sso_flow import run_sso_flow

log = get_logger("Handlers")

DARK_FILES = [
    {"name": "YOUTUBE_4H", "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiQEFNMl9EMyBZT1VUVUJFIiwidmxlc3NUdW5uZWxDb25maWciOnsidjJyYXlDb25maWciOnsiaG9zdCI6Imdvb2dsZS5jb20iLCJwb3J0Ijo0NDMsInV1aWQiOiJhYWFhMTExMS1iYmJiLTRjY2MtOGRkZC1lZWVlZmZmZjAwMDAiLCJzZXJ2ZXJOYW1lSW5kaWNhdGlvbiI6Imdvb2dsZXZpZGVvLmNvbSIsIndzUGF0aCI6Ii9UZWxlZ3JhbS9AQU0yX0QzL0BBSE1BRDMyMTQiLCJ3c0hlYWRlckhvc3QiOiJhaG1lZC12aXAxLTQ0NTg4MjYxNDUzNi51cy1jZW50cmFsMS5ydW4uYXBwIn19fQ=="},
    {"name": "SNAPCHAT_4H", "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiU05BUENIQVRfNEhf8J-HuvCfh7giLCJ2bGVzc1R1bm5lbENvbmZpZyI6eyJ2MnJheUNvbmZpZyI6eyJob3N0IjoiZ29vZ2xlLmNvbSIsInBvcnQiOjQ0MywidXVpZCI6ImFhYWExMTExLWJiYmItNGNjYy04ZGRkLWVlZWVmZmZmMDAwMCIsInNlcnZlck5hbWVJbmRpY2F0aW9uIjoiYXBpLnNuYXBjaGF0LmNvbSIsIndzUGF0aCI6Ii9UZWxlZ3JhbS9AQU0yX0QzL0BBSE1BRDMyMTQiLCJ3c0hlYWRlckhvc3QiOiJhaG1lZC12aXAxLTEwMjc5NzcwNDc4OC51cy1jZW50cmFsMS5ydW4uYXBwIn0sImluamVjdENvbmZpZyI6eyJtb2RlIjoiUFJPWFkiLCJwcm94eUhvc3QiOiIxNTcuMjQwLjkuMzkiLCJwYXlsb2FkIjoiQ09OTkVDVCBbaG9zdF06W3BvcnRdIEhUVFAvMS4xW2NybGZdeC1jb25uZWN0ZWQtdG86IDM0LjE0My43Mi4yW2NybGZdcHJveHktY29ubmVjdGlvbjoga2VlcC1hbGl2ZVtjcmxmXWNvbm5lY3Rpb246IGtlZXAtYWxpdmVbY3JsZl11c2VyLWFnZW50OiBGQkFWLzAuMCBbY3JsZl14LWlvcmctYnNpZDogQEFNMl9EM1tjcmxmXVtjcmxmXSJ9fX0="},
    {"name": "FREE_4H", "uri": "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoiRlJFRV80SF_wn4e68J-HuCIsInZsZXNzVHVubmVsQ29uZmlnIjp7InYycmF5Q29uZmlnIjp7Imhvc3QiOiJhbHQxMy55dDMuZ2dwaHQuY29tIiwicG9ydCI6NDQzLCJ1dWlkIjoiYWFhYTExMTEtYmJiYi00Y2NjLThkZGQtZWVlZWZmZmYwMDAwIiwic2VydmVyTmFtZUluZGljYXRpb24iOiJhbHQxMy55dDMuZ2dwaHQuY29tIiwid3NQYXRoIjoiL1RlbGVncmFtL0BBTTJfRDMvQEFITUFEMzIxNCJ9LCJpbmplY3RDb25maWciOnsiZW5hYmxlZCI6dHJ1ZSwibW9kZSI6IlBST1hZIiwicHJveHlIb3N0IjoiMTU3LjI0MC45LjM5IiwicGF5bG9hZCI6IkNPTk5FQ1QgW2hvc3RdOltwb3J0XSBIVFRQLzEuMVtjcmxmXXgtY29ubmVjdGVkLXRvOiAzNC4xNDMuNzIuMltjcmxmXXByb3h5LWNvbm5lY3Rpb246IGtlZXAtYWxpdmVbY3JsZl1jb25uZWN0aW9uOiBrZWVwLWFsaXZlW2Nyb2ZdeC1pb3JnLWJzaWQ6IEBBTTJfRDNbY3JsZl1bY3JsZl0ifX19"}
]

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
        await update.message.reply_text(messages.WELCOME_ADMIN, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin=True), disable_web_page_preview=True)
        return

    await update.message.reply_text(messages.WELCOME_USER, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin=False), disable_web_page_preview=True)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    urls = extract_urls(text)
    
    if not urls: return await update.message.reply_text("⚠️ أرسل رابط SSO صحيح.")
    
    sso_url = urls[0]
    if "skills.google" not in sso_url and "qwiklabs" not in sso_url and "accounts.google.com" not in sso_url:
        return await update.message.reply_text("⚠️ الرابط لا يبدو من Google Skills.")

    default_image = "docker.io/ajndjd2/ahmed-vip1"
    msg = await update.message.reply_text("⏳ جاري التنفيذ... [0/6]")
    asyncio.create_task(run_deploy_task(update.effective_chat.id, user.id, sso_url, default_image, msg, context))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if data == "back_main":
        if is_admin(user.id):
            await query.message.edit_text(messages.WELCOME_ADMIN, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(True), disable_web_page_preview=True)
        else:
            await query.message.edit_text(messages.WELCOME_USER, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(False), disable_web_page_preview=True)
            
    elif data == "admin" and is_admin(user.id):
        await query.message.edit_text("⚙️ لوحة الأدمن:", reply_markup=admin_menu())
    elif data == "admin_stats" and is_admin(user.id):
        total = await db.count_jobs()
        users = await db.get_all_users()
        await query.message.edit_text(f"📊 *إحصائيات:*\n\n👥 المستخدمين: {len(users)}\n🔧 المهام: {total}", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_menu())

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if extract_urls(text):
        await handle_url(update, context)
        return
    await update.message.reply_text("ℹ️ أرسل رابط Qwiklabs SSO للبدء.")

async def run_deploy_task(chat_id, user_id, sso_url, image, msg, context):
    browser = StealthBrowser()
    try:
        ctx = await browser.start()
        result = await run_sso_flow(ctx, sso_url, image=image, sender=msg)
        
        if result.get("success"):
            domain = result.get("domain")
            flag = result.get("flag", "🌍")
            await db.add_job(user_id, sso_url)
            
            try: await msg.delete()
            except: pass
            
            await context.bot.send_message(chat_id=chat_id, text=f"✅ <b>تم النشر بنجاح!</b>\n\n🌐 رابط run.app:\n<code>{result['final_url']}</code>", parse_mode=ParseMode.HTML)
            
            for dark in DARK_FILES:
                new_uri = build_darktunnel_uri_with_host(dark["uri"], domain)
                if new_uri:
                    bio = io.BytesIO(new_uri.encode("utf-8"))
                    bio.name = f"{dark['name']}_{flag} - {domain}.dark"
                    await context.bot.send_document(chat_id=chat_id, document=bio, filename=bio.name)
        else:
            try: await msg.delete()
            except: pass
            err_code = result.get("error", "")
            detail = result.get("message", "")
            
            if err_code == "service_already_exists": error_msg = "❌ توقف النشر: يوجد خدمة تعمل بنفس الاسم.\nيرجى إرسال رابط SSO جديد."
            elif err_code == "invalid_docker_image": error_msg = "❌ فشل إدخال صورة Docker.\nتأكد من الرابط أو أعد المحاولة."
            elif err_code == "image_field_empty": error_msg = "❌ فشل العثور على حقل الحاوية.\nقد يكون هناك ضغط على Google."
            else: error_msg = f"❌ فشل النشر:\n{detail or 'حدث خطأ غير متوقع.'}"
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
                
    except Exception as e:
        try: await msg.delete()
        except: pass
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطأ: {str(e)[:100]}")
    finally:
        await browser.close()
