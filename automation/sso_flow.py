import re
import asyncio
import os
from urllib.parse import urlparse
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
        
        # ✅ 1. تسجيل الدخول
        await update_msg("1) فتح رابط الطالب...")
        try: 
            await page.goto(sso_url, wait_until="networkidle", timeout=60000)
        except: 
            await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # نعطيو وقت للتحويلات باش تكمل
        await page.wait_for_timeout(5000)
        
        # فحص إذا كان يحتاج باسورد (باستعمال locator عوض evaluate)
        try:
            password_input = page.locator('input[type="password"]').first
            # كيتسنا 3 ثواني، إلا لقى الحقل كيرجع True
            if await password_input.is_visible(timeout=3000):
                if not password:
                    return {"success": False, "error": "need_password"}
                
                await update_msg("2) جاري إدخال كلمة السر...")
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
        except Exception as e:
            log.info(f"لا يوجد حقل باسورد أو تم تجاوزه: {e}")

        await update_msg("3) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")

        await update_msg("4) قبول الشروط...")
        await console.step2_tos_and_country(page)

        # ✅ 2. استخراج الـ Token
        await update_msg("5) استخراج بيانات الدخول...")
        
        access_token = None
        
        def capture_token(request):
            nonlocal access_token
            if "googleapis.com" in request.url and not access_token:
                auth = request.headers.get("authorization")
                if auth and auth.startswith("Bearer "):
                    access_token = auth.replace("Bearer ", "")

        page.on("request", capture_token)
        
        # نطلبوا صفحة باش المتصفح يبعت طلبات فيها الـ Token
        try:
            await page.goto("https://console.cloud.google.com/welcome", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            log.warning(f"مشكل فـ جلب التوكن: {e}")

        if not access_token:
            return {"success": False, "error": "❌ فشل استخراج الـ Token من المتصفح."}

        # ✅ 3. النشر عبر API
        await update_msg("6) جاري النشر عبر Google API...")
        
        final_url = await asyncio.to_thread(deploy_cloud_run, project_id, access_token)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        
        # ما نصوروش إلا كان الخطأ هو تحويل الصفحة
        if page and not page.is_closed() and "Execution context was destroyed" not in err_str:
            try:
                await page.wait_for_timeout(2000)
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(path)
            except: pass
            
        # إلا كان خطأ التحويل، نرجعو رسالة واضحة للمستخدم
        if "Execution context was destroyed" in err_str:
            err_str = "❌ حدث تحويل مفاجئ في الصفحة. يرجى إعادة المحاولة."
            
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
