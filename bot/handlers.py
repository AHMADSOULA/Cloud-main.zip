import asyncio
import io
import base64
import json
import os
import re
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

DARKTUNNEL_BASE_URI = "darktunnel://eyJ0eXBlIjoiVkxFU1MiLCJuYW1lIjoi2YXYrNin2YbZiiDYp9iz2YrYpyDZiCDYp9ir2YrYsSAiLCJ2bGVzc1R1bm5lbENvbmZpZyI6eyJ2MnJheUNvbmZpZyI6eyJob3N0IjoiYWx0MTMueXQzLmdncGh0LmNvbSIsInBvcnQiOjQ0MywidXVpZCI6ImFhYWExMTExLWJiYmItNGNjYy04ZGRkLWVlZWVmZmZmMDAwMCIsInNlcnZlck5hbWVJbmRpY2F0aW9uIjoiYWx0MTMueXQzLmdncGh0LmNvbSIsIndzUGF0aCI6Ii9UZWxlZ3JhbS9AQU0yX0QzL0BBSE1BRDMyMTQiLCJ3c0hlYWRlckhvc3QiOiJhaG1lZC12aXAxLTQxNDAwODYxMjEyMy5ldXJvcGUtd2VzdDEucnVuLmFwcCJ9LCJpbmplY3RDb25maWciOnsiZW5hYmxlZCI6dHJ1ZSwibW9kZSI6IlBST1hZIiwicHJveHlIb3N0IjoiMTU3LjI0MC45LjM5IiwicGF5bG9hZCI6IkNPTk5FQ1QgW2hvc3RdOltwb3J0XSBIVFRQLzEuMVtjcmxmXXgtY29ubmVjdGVkLXRvOiAzNC4xNDMuNzIuMltjcmxmXXByb3h5LWNvbm5lY3Rpb246IGtlZXAtYWxpdmVbY3JsZl1jb25uZWN0aW9uOiBrZWVwLWFsaXZlW2Nyb2ZdeC1pb3JnLWJzaWQ6IEBBTTJfRDNbY3JsZl1bY3JsZl0ifX19"

_user_locks: dict[int, asyncio.Lock] = {}

def _get_lock(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock

def _b64_pad(s: str) -> str:
    return s + ("=" * ((4 - (len(s) % 4)) % 4)) if s else s

def build_darktunnel_uri_with_host(new_host: str) -> str:
    try:
        b64 = _b64_pad(DARKTUNNEL_BASE_URI.split("darktunnel://", 1)[1].strip())
        data = json.loads(base64.b64decode(b64.encode("utf-8")).decode("utf-8"))
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

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    
    session = await db.get_session(user.id)
    if session and session.get("state") == "waiting_password":
        await handle_password(update, context)
        return

    urls = extract_urls(text)
    if urls:
        user_id = user.id
        chat_id = update.effective_chat.id
        sso_url = urls[0]
        asyncio.create_task(_safe_deploy(context, user_id, chat_id, sso_url))
        return
        
    await update.message.reply_text("ℹ️ أرسل رابط Qwiklabs SSO للبدء.")

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    password = (update.message.text or "").strip()
    if not password: return

    session = await db.get_session(user.id)
    if not session or session.get("state") != "waiting_password": return

    sso_url = session.get("sso_url")
    await db.clear_session(user.id)

    try: await update.message.delete()
    except: pass

    asyncio.create_task(_safe_deploy(context, user.id, update.effective_chat.id, sso_url, password=password))

async def _safe_deploy(context, user_id, chat_id, sso_url, password=None):
    lock = _get_lock(user_id)
    if lock.locked():
        await context.bot.send_message(chat_id=chat_id, text="⏳ عندك عملية نشر جارية، عاود من بعد ما تكمل.")
        return
    async with lock:
        await process_deploy(context, user_id, chat_id, sso_url, password=password)

async def process_deploy(context, user_id, chat_id, sso_url, password=None):
    status_msg = await context.bot.send_message(
        chat_id=chat_id, 
        text="✅ تم استلام الرابط. جاري التنفيذ الآن...\n"
    )
    
    image_uri = "docker.io/ajndjd2/ahmed-vip1" 
    service_name = image_uri.split("/")[-1].split(":")[0] 
    
    browser = StealthBrowser()
    try:
        ctx = await browser.start()
        result = await run_sso_flow(ctx, context.bot, chat_id, sso_url, status_msg, password, image_uri=image_uri)
        
        if result.get("success"):
            domain = result.get("domain")
            region = result.get("region", "us-central1")
            elapsed = result.get("time_taken", 0)
            new_uri = build_darktunnel_uri_with_host(domain)
            
            success_text = (
                f"🎉 تم النشر بنجاح!\n\n"
                f"🏷️ الخدمة: `{service_name}`\n"
                f"📦 الصورة: `{service_name}`\n"
                f"🚀 الرابط:\nhttps://{domain}\n"
                f"📍 المنطقة: `{region}`\n"
                f"⚡ الوقت: {elapsed} ثانية"
            )
            
            try: await status_msg.delete()
            except: pass
            
            await context.bot.send_message(
                chat_id=chat_id, 
                text=success_text, 
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            
            if new_uri:
                safe_domain = re.sub(r"[^a-z0-9\.\-]+", "_", domain.lower()).strip("_")
                tg_fname = f"زين و اسيا مجاني - {safe_domain}.dark"
                bio = io.BytesIO(new_uri.encode("utf-8"))
                bio.name = tg_fname 
                await context.bot.send_document(chat_id=chat_id, document=bio, filename=tg_fname)
                
        else:
            err = result.get("error", "")
            if err == "need_password":
                try: await status_msg.delete()
                except: pass
                
                await db.set_session(user_id, sso_url=sso_url, state="waiting_password")
                await context.bot.send_message(chat_id=chat_id, text="🔑 مطلوب كلمة السر\n\nأرسل كلمة السر هنا:")
                return
            elif "SERVICE_EXISTS" in err or "الخدمة موجودة" in err:
                # الرسالة المطلوبة عند وجود الخدمة
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text="⏭️ تم تخطي دورك بسبب: يوجد خدمة مفعلة بنفس اسم هذه الرابط.\n\nيرجى إرسال رابط SSO جديد."
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"⏭️ تم تخطي دورك بسبب التجمد.\nالسبب: {err[:200]}\n\nيمكنك إرسال الرابط مجدداً."
                )
                
    except Exception as e:
        try: await status_msg.delete()
        except: pass
        await context.bot.send_message(chat_id=chat_id, text=f"❌ توقف الخدمة\nخطأ: `{str(e)[:300]}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        await browser.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_main":
        await query.message.edit_text(messages.WELCOME_USER, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_admin(query.from_user.id)))
