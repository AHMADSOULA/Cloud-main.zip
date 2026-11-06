import re
import asyncio
from urllib.parse import urlparse, parse_qs

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

def extract_authuser(page_url: str) -> str:
    try:
        qs = parse_qs(urlparse(page_url).query)
        return qs.get('authuser', ['1'])[0]
    except Exception:
        return '1'

def _has_password(url: str) -> bool:
    return "password=" in (url or "").lower()

async def _is_blocked(page) -> str:
    try:
        # ✅ فحص سريع جداً للـ URL باش نمسكو الحساب المحذوف
        url = page.url.lower()
        if "accountdeleted" in url or "deletedaccount" in url:
            return "account_deleted"
        
        # ✅ فحص محتوى الصفحة بجافاسكريبت
        result = await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                const body = (document.body.innerText || '').toLowerCase();

                if (body.includes('account deleted') || 
                    body.includes('account has been deleted') || 
                    body.includes('this account was recently deleted')) {
                    return 'account_deleted';
                }
                
                if (body.includes("couldn't find your google account") || 
                    body.includes("couldn't sign you in")) {
                    return 'signin';
                }

                if (body.includes('session expired') || 
                    body.includes('no longer valid') || 
                    body.includes('link you followed has expired')) {
                    return 'expired';
                }
                
                if (body.includes('something went wrong')) {
                    return 'something_went_wrong';
                }

                return null;
            }
        """)
        return result
    except Exception:
        return None

async def _is_dashboard(page) -> bool:
    try:
        url = page.url.lower()
        # ✅ إلا مازال فـ AddsSession أو صفحة خطأ، ماشي Dashboard
        if "addsession" in url or "accountdeleted" in url or "signin" in url:
            return False
            
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                if (url.includes('console.cloud.google.com')) {
                    const body = (document.body.innerText || '').toLowerCase();
                    // إلا كان النص فيه "Welcome" أو "Dashboard" أو "Project info"
                    return body.includes('dashboard') || body.includes('project info') || body.includes('welcome');
                }
                return false;
            }
        """)
    except Exception:
        return False

async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    region = "us-central1" if _has_password(sso_url) else "europe-west1"
    flag = "🇺🇸" if _has_password(sso_url) else "🇧🇪"

    console = CloudConsole(context, sender=sender, user_tag=user_tag)
    status_msg = await sender.reply_text("🚀 جاري التنفيذ... [0/8]") if sender else None

    async def handle_error(err_code, extra_msg=""):
        if status_msg:
            try: await status_msg.delete()
            except: pass
        await console._shot(page, "") # صورة نظيفة بلا كابسيون
        return {"success": False, "error": err_code, "message": extra_msg}

    page = await context.new_page()
    try:
        # 1. فتح الرابط
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [1/8] فتح الرابط")
        try:
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            await page.goto(sso_url, wait_until="commit", timeout=60000)

        # ✅ فحص فوري بعد التحميل
        await page.wait_for_timeout(3000)
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        # 2. TOS
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [2/8] TOS")
        try:
            await console.step1_welcome_screen(page)
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

        await page.wait_for_timeout(1500)
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        # 3. Terms
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [3/8] Terms Dialog")
        try:
            await console.step2_terms_dialog(page)
        except Exception as e:
            log.warning(f"⚠️ step2: {e}")

        # 4. Dashboard (نستناو بسرعة كل 0.5 ثانية)
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [4/8] Dashboard")
        dashboard_ok = False
        for _ in range(30): # 30 * 0.5s = 15s max wait
            await page.wait_for_timeout(500)
            blocked = await _is_blocked(page)
            if blocked: return await handle_error(blocked)
            if await _is_dashboard(page):
                dashboard_ok = True
                break

        if not dashboard_ok:
            return await handle_error("no_dashboard", "❌ لم يتم الوصول للوحة التحكم (تأكد من الرابط)")

        authuser = extract_authuser(page.url)
        
        # 5. Enable API
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [5/8] تفعيل API")
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            log.warning(f"⚠️ step3: {e}")

        # 6. Create Cloud Run
        if status_msg: await status_msg.edit_text(f"🚀 جاري التنفيذ... [6/8] إنشاء Cloud Run {flag}")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            err_str = str(e)
            if "service_already_exists" in err_str:
                return await handle_error("service_already_exists")
            else:
                return await handle_error("step4_failed", err_str[:200])

        # 7. Get URL
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [7/8] انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            return await handle_error("step5_failed", str(e)[:200])

        if status_msg: await status_msg.delete()
        return {"success": True, "project_id": project_id, "authuser": authuser, "final_url": final_url, "domain": domain, "region": region, "flag": flag}
    finally:
        await page.close()
