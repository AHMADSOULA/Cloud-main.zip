import asyncio
import io
import base64
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot import messages
from bot.keyboards import main_menu, admin_menu, containers_menu, my_account_menu
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
    inviter_id = None
    if context.args and len(context.args) > 0:
        try: inviter_id = int(context.args[0])
        except: pass

    is_new = await db.is_user_new(user.id)
    await db.register_user(user.id, user.username or user.first_name)
    
    if is_new and inviter_id and inviter_id != user.id:
        success = await db.add_invite(inviter_id, user.id)
        if success:
            await db.update_points(inviter_id, 2)
            try:
                await context.bot.send_message(chat_id=inviter_id, text="🎉 مبروك! شخص جديد دخل عبر رابط الدعوة ديالك، تمت إضافة **2 نقطة** لحسابك.", parse_mode=ParseMode.MARKDOWN)
            except: pass

    text = f"أهلاً بك يا <b>{user.first_name}</b> في <b>Cloud Run</b> ☁️✨\n\n📥 أرسل رابط Qwiklabs SSO للبدء، أو اختر من القائمة:"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu(is_admin(user.id)))

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    urls = extract_urls(text)
    
    if not urls: return await update.message.reply_text("⚠️ أرسل رابط SSO صحيح.")
    
    sso_url = urls[0]
    u = await db.get_user(user.id)
    cost = 0 if u['deploy_count'] == 0 else 3
    
    if cost > 0 and u['points'] < cost and not is_admin(user.id):
        return await update.message.reply_text(f"❌ ليس لديك نقاط كافية. كل نشر يكلف {cost} نقاط.\nتواصل مع الأدمن لشحن رصيدك.")

    await db.set_session(user.id, state="waiting_container", sso_url=sso_url)
    containers = await db.get_user_containers(user.id)
    
    if not containers:
        return await update.message.reply_text(
            "⚠️ ليس لديك حاويات (Docker). يرجى إضافة حاوية أولاً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ إضافة حاوية", callback_data="add_docker")]])
        )
        
    await update.message.reply_text("✅ تم استلام الرابط.\nالآن اختر الحاوية التي تريد النشر عليها:", reply_markup=containers_menu(containers))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if data == "back_main":
        await query.message.edit_text(f"أهلاً بك يا <b>{user.first_name}</b> في <b>Cloud Run</b> ☁️✨\n\n📥 أرسل رابط Qwiklabs SSO للبدء، أو اختر من القائمة:", parse_mode=ParseMode.HTML, reply_markup=main_menu(is_admin(user.id)))
        
    elif data == "my_account":
        u = await db.get_user(user.id)
        text = (
            f"👤 حسابي ونظام الدعوات\n\n"
            f"🌍 نقاطك الحالية: {u['points']} نقطة\n"
            f"🚀 عمليات النشر الناجحة: {u['deploy_count']}\n\n"
            f"💡 كيف يعمل النظام؟\n"
            f"- أول عملية نشر لك مجانية 🎁\n"
            f"- كل عملية نشر تكلف 3 نقاط.\n"
            f"- في حال فشل النشر، تُعاد النقاط لحسابك تلقائياً.\n"
            f"- كل شخص تدعوه عبر رابطك يمنحك نقطتين (2).\n\n"
            f"🔗 رابط الدعوة الخاص بك:\n"
            f"<code>https://t.me/cloudahmedbot?start={user.id}</code>"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu(is_admin(user.id)))

    elif data == "new_deploy":
        await query.message.edit_text("📥 أرسل رابط Qwiklabs SSO للبدء:")

    elif data == "my_containers":
        containers = await db.get_user_containers(user.id)
        list_text = "\n".join([f"📦 {c['name']} → <code>{c['image']}</code>" for c in containers]) or "لا توجد حاويات."
        await query.message.edit_text(f"🖌️ <b>حاوياتك الخاصة:</b>\n\n{list_text}\n\nيمكنك إدارة حاوياتك:", parse_mode=ParseMode.HTML, reply_markup=my_account_menu())
        
    elif data == "add_docker":
        await db.set_session(user.id, state="waiting_docker_name")
        await query.message.edit_text("📝 أرسل <b>اسم</b> الحاوية (مثال: `MyDocker`):", parse_mode=ParseMode.HTML)
        
    elif data == "del_docker":
        containers = await db.get_user_containers(user.id)
        if not containers: return await query.message.edit_text("❌ لا توجد حاويات للحذف.")
        rows = [[InlineKeyboardButton(f"❌ {c['name']}", callback_data=f"del_{c['id']}")] for c in containers]
        rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_containers")])
        await query.message.edit_text("🗑️ اختر الحاوية للحذف:", reply_markup=InlineKeyboardMarkup(rows))
        
    elif data.startswith("del_"):
        c_id = int(data.split("_")[1])
        await db.delete_container(c_id, user.id)
        await query.message.edit_text("✅ تم حذف الحاوية.", reply_markup=my_account_menu())

    elif data.startswith("use_docker_"):
        c_id = int(data.split("_")[2])
        containers = await db.get_user_containers(user.id)
        container = next((c for c in containers if c['id'] == c_id), None)
        
        if not container: return await query.message.edit_text("❌ الحاوية غير موجودة.")
            
        session = await db.get_session(user.id)
        if not session or not session.get('sso_url'): return await query.message.edit_text("❌ لم يتم العثور على رابط SSO، أعد إرساله.")
            
        sso_url = session['sso_url']
        await db.clear_session(user.id) 
        
        u = await db.get_user(user.id)
        cost = 0 if u['deploy_count'] == 0 else 3
        
        if cost > 0 and not is_admin(user.id):
            await db.update_points(user.id, -cost)
        
        await query.message.edit_text(f"🚀 بدأ النشر باستخدام حاوية: <b>{container['name']}</b>\n⏳ جاري التنفيذ...", parse_mode=ParseMode.HTML)
        
        asyncio.create_task(run_deploy_task(query.message.chat_id, user.id, sso_url, container['image'], query.message, context, cost))

    elif data == "admin_panel":
        if not is_admin(user.id): return
        await query.message.edit_text("⚙️ لوحة الأدمن:", reply_markup=admin_menu())
        
    elif data == "admin_users":
        if not is_admin(user.id): return
        users = await db.get_all_users()
        text = "👥 <b>إحصائيات المستخدمين:</b>\n\n"
        for u in users:
            text += f"🆔 <code>{u['user_id']}</code>\n💳 نقاط: {u['points']} | 🚀 نشر: {u['deploy_count']} | 🤝 دعوات: {u['invites_count']}\n──────────\n"
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())
        
    elif data == "admin_send_points":
        if not is_admin(user.id): return
        await db.set_session(user.id, state="admin_waiting_points_id")
        await query.message.edit_text("💳 أرسل <b>ID المستخدم</b> الذي تريد شحنه:", parse_mode=ParseMode.HTML)

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    session = await db.get_session(user.id)
    
    if session and session.get("state") == "waiting_docker_name":
        await db.set_session(user.id, state="waiting_docker_image")
        context.user_data['temp_name'] = text
        return await update.message.reply_text("📝 الآن أرسل <b>صورة Docker</b> (مثال: `docker.io/user/repo:tag`):", parse_mode=ParseMode.HTML)
        
    if session and session.get("state") == "waiting_docker_image":
        name = context.user_data.get('temp_name', 'Docker1')
        await db.add_container(user.id, name, text)
        await db.clear_session(user.id)
        return await update.message.reply_text("✅ تم إضافة الحاوية بنجاح.", reply_markup=main_menu(is_admin(user.id)))

    if extract_urls(text):
        await handle_url(update, context)
        return
        
    if is_admin(user.id) and session and session.get("state") == "admin_waiting_points_id":
        context.user_data['target_id'] = text
        await db.set_session(user.id, state="admin_waiting_points_amount")
        return await update.message.reply_text("💳 شحال من نقطة؟ (أرسل رقم):")
        
    if is_admin(user.id) and session and session.get("state") == "admin_waiting_points_amount":
        try:
            target_id = int(context.user_data.get('target_id'))
            amount = int(text)
            await db.update_points(target_id, amount)
            await db.clear_session(user.id)
            await update.message.reply_text(f"✅ تم إرسال {amount} نقطة للمستخدم `{target_id}`.", reply_markup=admin_menu())
        except:
            await update.message.reply_text("❌ خطأ، أعد المحاولة.")
        return

    await update.message.reply_text("ℹ️ أرسل /start للبدء.")

async def run_deploy_task(chat_id, user_id, sso_url, image, msg, context, cost):
    browser = StealthBrowser()
    try:
        ctx = await browser.start()
        result = await run_sso_flow(ctx, sso_url, image=image, sender=msg, user_tag="user")
        
        if result.get("success"):
            domain = result.get("domain")
            flag = result.get("flag", "🌍")
            await db.increment_deploy(user_id)
            
            await msg.edit_text(f"✅ <b>تم النشر بنجاح!</b>\n\n🌐 رابط run.app:\n<code>{result['final_url']}</code>", parse_mode=ParseMode.HTML)
            
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
            refund_text = ""
            
            if cost > 0 and not is_admin(user_id):
                await db.update_points(user_id, cost)
                refund_text = "\nتم اعادة نقاط"
            
            if err_code == "account_deleted":
                error_msg = f"delete account ❌{refund_text}"
            elif err_code == "signin":
                error_msg = f"SSO منتهي ❌{refund_text}"
            elif err_code == "expired":
                error_msg = f"الرابط منتهي ❌{refund_text}"
            elif err_code == "no_dashboard":
                error_msg = f"لم يتم الوصول للوحة التحكم ❌{refund_text}"
            elif err_code == "image_field_empty":
                error_msg = f"❌ فشل إدخال صورة Docker\nجرب حاوية أخرى أو رابط SSO جديد.{refund_text}"
            elif err_code == "service_already_exists":
                error_msg = f"❌ توقف النشر\nيوجد خدمة تعمل بنفس الاسم حالياً.\nيرجى الانتظار حتى تنتهي الخدمة الحالية، أو إرسال رابط SSO جديد.{refund_text}"
            else:
                error_msg = f"❌ فشل النشر:\n{result.get('message')}{refund_text}"
            
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
                
    except Exception as e:
        try: await msg.delete()
        except: pass
        if cost > 0 and not is_admin(user_id):
            await db.update_points(user_id, cost)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطأ: {str(e)[:100]}\nتم اعادة نقاط")
    finally:
        await browser.close()
