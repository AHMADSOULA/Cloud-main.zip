import re
import asyncio
import os
from urllib.parse import urlparse, parse_qs, unquote
from automation.console import CloudConsole
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

def extract_email_from_url(url: str) -> str:
    try:
        m = re.search(r'Email%3D([^%&]+%40qwiklabs\.net)', url or "")
        if m: return unquote(m.group(1))
        m = re.search(r'Email=([^&\s#]+@qwiklabs\.net)', url or "")
        if m: return m.group(1)
        m = re.search(r'([a-zA-Z0-9\.\-]+@qwiklabs\.net)', url or "")
        if m: return m.group(1)
    except: pass
    return None

def extract_password_from_url(url: str) -> str:
    try:
        m = re.search(r'Password=([^&\s#]+)', url or "")
        if m: return unquote(m.group(1))
    except: pass
    return None

def _has_password(url: str) -> bool:
    return "password=" in (url or "").lower()

async def _is_blocked(page) -> str:
    try:
        url = page.url.lower()
        if "accountdeleted" in url or "deletedaccount" in url: 
            return "account_deleted"
        result = await page.evaluate("""
            () => {
                const body = (document.body.innerText || '').toLowerCase();
                if (body.includes('account deleted') || body.includes('account has been deleted')) return 'account_deleted';
                if (body.includes('session expired') || body.includes('invalid link')) return 'expired';
                return null;
            }
        """)
        return result
    except: return None

async def run_sso_flow(context, bot, chat_id, sso_url: str, image: str, status_msg=None, password=None) -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    # إذا كان الباسورد موجود فالرابط، كناخدوه
    if not password:
        password = extract_password_from_url(sso_url)

    region = "us-central1" if _has_password(sso_url) else "europe-west1"
    
    console = CloudConsole(context)
    page = None
    current_step = "البداية"

    async def update_status(step, text=""):
        nonlocal current_step
        current_step = f"[{step}/6] {text}"
        if status_msg:
            try: await status_msg.edit_text(f"⏳ جاري التنفيذ... {current_step}")
            except: pass

    try:
        page = await context.new_page()
        
        # 1. فتح الرابط واكتشاف تسجيل الدخول
        await update_status(1, "فتح الرابط")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        await page.wait_for_timeout(3000)
        
        # ✅ اكتشاف صفحة تسجيل الدخول
        if "accounts.google.com" in page.url or "signin" in page.url:
            log.info("🔍 كاين تسجيل دخول")
            
            # نعمر الإيميل إلا كان خاوي
            email = extract_email_from_url(sso_url)
            if email:
                try:
                    email_input = page.locator('input[type="email"]')
                    if await email_input.is_visible(timeout=2000):
                        await email_input.fill(email)
                        await page.wait_for_timeout(500)
                except: pass

            # نضغطو Next
            try:
                next_btn = page.get_by_role("button", name="Next")
                if await next_btn.is_visible(timeout=3000):
                    await next_btn.click()
                    await page.wait_for_timeout(3000)
            except: pass
            
            # نتأكدو واش طلب الباسورد
            is_password = await page.evaluate("() => !!document.querySelector('input[type=\"password\"]')")
            
            if is_password:
                if password:
                    log.info("🔑 كنكتبو الباسورد")
                    await page.fill('input[type="password"]', password)
                    await page.wait_for_timeout(500)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(5000)
                    
                    still_password = await page.evaluate("() => !!document.querySelector('input[type=\"password\"]')")
                    if still_password:
                        raise Exception("wrong_password")
                else:
                    raise Exception("need_password")

        # ✅ فحص الحساب المحذوف
        blocked = await _is_blocked(page)
        if blocked: raise Exception(blocked)

        # 2. TOS
        await update_status(2, "قبول التوجيهات")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

        # ✅ فحص بعد التوجيهات
        blocked = await _is_blocked(page)
        if blocked: raise Exception(blocked)

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 3. Terms
        await update_status(3, "قبول الشروط")
        await console.step2_tos_and_country(page)

        # 4. Enable API
        await update_status(4, "تفعيل API")
        await console.step3_enable_api(page, project_id, authuser)

        # 5. Create Cloud Run
        await update_status(5, "إنشاء الخدمة")
        await console.step4_create_cloud_run(page, project_id, authuser, image)

        # 6. Get URL
        await update_status(6, "انتظار الرابط")
        final_url = await console.step5_get_deployed_url(page)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ فشل في الخطوة {current_step}: {err_str}")
        
        # التصوير عند الأخطاء فقط (بلا كابسيون، الصورة بوحدها)
        if page and not page.is_closed() and err_str not in ["need_password", "wrong_password"]:
            try:
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(path)
            except Exception as shot_err:
                log.error(f"فشل التصوير: {shot_err}")
        
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
