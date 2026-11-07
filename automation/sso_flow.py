import re
import asyncio
import os
from urllib.parse import urlparse, parse_qs
from automation.console import CloudConsole
from automation.api_deployer import deploy_cloud_run
from utils.logger import get_logger

log = get_logger("SSOFlow")

def extract_project_id(url: str) -> str:
    m = re.search(r'(qwiklabs-gcp-[\w-]+)', url or "")
    return m.group(1) if m else None

def extract_domain_from_service_url(service_url: str) -> str:
    s = (service_url or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        return urlparse(s).netloc.strip()
    return s.replace("http://", "").replace("https://", "").split("/")[0].strip()

async def run_sso_flow(context, bot, chat_id, sso_url: str, status_msg=None, password=None):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    console = CloudConsole(context)
    page = None

    async def update_msg(text):
        if status_msg:
            try: await status_msg.edit_text(text)
            except: pass

    try:
        page = await context.new_page()
        
        # ✅ 1. تسجيل الدخول عبر المتصفح
        await update_msg("1) فتح رابط الطالب...")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        await page.wait_for_timeout(3000)
        
        # فحص إذا كان يحتاج باسورد
        if "accounts.google.com" in page.url or "signin" in page.url:
            is_password = await page.evaluate("() => !!document.querySelector('input[type=\"password\"]')")
            if is_password:
                if not password:
                    return {"success": False, "error": "need_password"}
                await page.fill('input[type="password"]', password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)

        await update_msg("2) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")

        await update_msg("3) قبول الشروط...")
        await console.step2_tos_and_country(page)

        # ✅ 2. استخراج الـ Token من المتصفح
        await update_msg("4) استخراج بيانات الدخول (Token)...")
        
        access_token = None
        
        # دالة مساعدة لالتقاط الـ Token من طلبات الشبكة
        def capture_token(request):
            nonlocal access_token
            if "googleapis.com" in request.url and not access_token:
                auth = request.headers.get("authorization")
                if auth and auth.startswith("Bearer "):
                    access_token = auth.replace("Bearer ", "")

        page.on("request", capture_token)
        
        # نعملو طلب بسيط باش يبدا المتصفح يصيفط طلبات فيها الـ Token
        try:
            await page.goto("https://console.cloud.google.com/welcome", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
        except:
            pass

        if not access_token:
            return {"success": False, "error": "❌ فشل استخراج الـ Token من المتصفح."}

        # ✅ 3. النشر عبر API
        await update_msg("5) جاري النشر عبر Google API...")
        
        # كنستعملو asyncio.to_thread باش ما نبلوكيوش البوت
        final_url = await asyncio.to_thread(deploy_cloud_run, project_id, access_token)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        if page and not page.is_closed():
            try:
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(path)
            except: pass
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
