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
    except Exception:
        return None

async def _is_dashboard(page) -> bool:
    try:
        url = page.url.lower()
        if "addsession" in url or "accountdeleted" in url or "signin" in url:
            return False
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                if (url.includes('console.cloud.google.com')) {
                    const body = (document.body.innerText || '').toLowerCase();
                    return body.includes('dashboard') || body.includes('project info');
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
        await console._shot(page, "")
        return {"success": False, "error": err_code, "message": extra_msg}

    page = await context.new_page()
    try:
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [1/8] فتح الرابط")
        try:
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            await page.goto(sso_url, wait_until="commit", timeout=60000)

        await page.wait_for_timeout(3000)
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [2/8] TOS")
        try: await console.step1_welcome_screen(page)
        except: pass
        await page.wait_for_timeout(1500)
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [3/8] Terms Dialog")
        try: await console.step2_terms_dialog(page)
        except: pass

        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [4/8] Dashboard")
        dashboard_ok = False
        for _ in range(30): 
            await page.wait_for_timeout(500)
            blocked = await _is_blocked(page)
            if blocked: return await handle_error(blocked)
            if await _is_dashboard(page):
                dashboard_ok = True
                break

        if not dashboard_ok:
            return await handle_error("no_dashboard", "❌ لم يتم الوصول للوحة التحكم")

        authuser = extract_authuser(page.url)
        
        if status_msg: await status_msg.edit_text("🚀 جاري التنفيذ... [5/8] تفعيل API")
        try: await console.step3_enable_api(page, project_id, authuser)
        except: pass

        if status_msg: await status_msg.edit_text(f"🚀 جاري التنفيذ... [6/8] إنشاء Cloud Run {flag}")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            err_str = str(e)
            if "service_already_exists" in err_str:
                return await handle_error("service_already_exists")
            elif "image_field_empty" in err_str:
                return await handle_error("image_field_empty")
            else:
                return await handle_error("step4_failed", err_str[:200])

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
