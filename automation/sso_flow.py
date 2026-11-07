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
    except: return '1'

def _has_password(url: str) -> bool:
    return "password=" in (url or "").lower()

async def _is_dashboard(page) -> bool:
    try:
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                if (url.includes('console.cloud.google.com') && !url.includes('signin') && !url.includes('accounts.google.com')) {
                    const body = (document.body.innerText || '').toLowerCase();
                    if (body.includes('sign in') && body.includes('google account')) return false;
                    if (body.includes('account deleted')) return false;
                    return true;
                }
                return false;
            }
        """)
    except: return False

async def _is_blocked(page) -> str:
    try:
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                const body = (document.body.innerText || '').toLowerCase();
                if (body.includes('account deleted') || body.includes('account has been deleted') || body.includes('this account was recently deleted')) return 'account_deleted';
                if (url.includes('accounts.google.com/signin') && !url.includes('addsession')) return 'signin';
                if (body.includes('session expired') || body.includes('no longer valid') || body.includes('invalid link') || body.includes('sign in to continue') || body.includes('link you followed has expired')) return 'expired';
                return null;
            }
        """)
    except: return None

async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        raise RuntimeError("❌ Project ID ماكانش في الرابط.")

    if _has_password(sso_url):
        region = "us-central1"
        flag = "🇺🇸"
    else:
        region = "europe-west1"
        flag = "🇧🇪"

    console = CloudConsole(context, sender=sender, user_tag=user_tag)

    async def update_status(step, text=""):
        if not sender: return
        try:
            await sender.edit_text(f"[{user_tag}] • {step}) {text}")
        except: pass

    page = await context.new_page()
    try:
        await update_status("1", "فتح رابط الطالب")
        try:
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except:
            await page.goto(sso_url, wait_until="commit", timeout=60000)

        await page.wait_for_timeout(2500)
        blocked = await _is_blocked(page)
        if blocked:
            await console._shot(page, f"❌ {blocked}")
            return {"success": False, "error": blocked, "message": "account_deleted" if blocked == 'account_deleted' else "❌ SSO منتهي"}

        await update_status("2", "✅")
        
        await update_status("3", f"✅ (Project: {project_id})")
        try:
            await console.step1_welcome_screen(page)
            await console.step2_terms_dialog(page)
        except Exception as e:
            log.warning(f"⚠️ TOS: {e}")

        await page.wait_for_timeout(1500)
        blocked = await _is_blocked(page)
        if blocked:
            return {"success": False, "error": blocked, "message": "account_deleted" if blocked == 'account_deleted' else "❌ SSO منتهي بعد TOS"}

        await update_status("4", "تفعيل Cloud Run API...")
        dashboard_ok = False
        for i in range(20):
            await page.wait_for_timeout(1000)
            if await _is_dashboard(page):
                dashboard_ok = True
                break

        if not dashboard_ok:
            return {"success": False, "error": "no_dashboard", "message": "❌ ما وصلناش Dashboard"}

        authuser = extract_authuser(page.url)
        
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            log.warning(f"⚠️ API: {e}")

        await update_status("5", "⚠️ API مؤكد، متابعة...")
        await update_status("6", "فتح Cloud Run...")
        await update_status("7", "✅")
        await update_status("8", "تعبئة الحقول...")
        
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            return {"success": False, "error": "step4_failed", "message": str(e)[:200]}

        await update_status("9", "✅")
        await update_status("10", "إنشاء الخدمة...")
        
        await page.wait_for_timeout(1000)
        await update_status("11", "✅ إنشاء")
        await update_status("12", "انتظار رابط النشر...")

        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            return {"success": False, "error": "step5_failed", "message": str(e)[:200]}

        if sender:
            try: await sender.delete()
            except: pass

    finally:
        try: await page.close()
        except: pass

    return {
        "success": True,
        "project_id": project_id,
        "authuser": authuser,
        "final_url": final_url,
        "domain": domain,
        "region": region,
        "flag": flag,
    }
