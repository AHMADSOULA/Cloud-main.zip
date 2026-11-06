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

async def run_sso_flow(context, sso_url: str, sender=None) -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    image = "docker.io/ajndjd2/ahmed-vip1"
    region = "europe-west1"
    flag = "🇧🇪"

    console = CloudConsole(context, sender=sender)
    
    async def update_status(text):
        if sender:
            try: await sender.edit_text(f"⏳ جاري التنفيذ... {text}")
            except: pass

    page = None
    try:
        page = await context.new_page()
        
        async def handle_error(err_code, extra_msg=""):
            if page: await console._shot(page, "📸 تفاصيل الخطأ:")
            return {"success": False, "error": err_code, "message": extra_msg}

        await update_status("[1/6] فتح الرابط")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)

        await page.wait_for_timeout(2000)
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        await update_status("[2/6] قبول الشروط")
        try: await console.step1_welcome_screen(page)
        except: pass
        await page.wait_for_timeout(1000)
        
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        await update_status("[3/6] Terms Dialog")
        try: await console.step2_terms_dialog(page)
        except: pass
        await page.wait_for_timeout(1000)

        await update_status("[4/6] تفعيل API")
        authuser = extract_authuser(page.url)
        try: await console.step3_enable_api(page, project_id, authuser)
        except: pass

        await update_status("[5/6] إنشاء Cloud Run")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            return await handle_error(str(e), str(e))

        await update_status("[6/6] انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            return await handle_error(str(e), str(e))

        return {"success": True, "final_url": final_url, "domain": domain, "flag": flag}

    except Exception as e:
        log.error(f"❌ خطأ فجائي: {e}")
        if page: await console._shot(page, "📸 تفاصيل الخطأ:")
        return {"success": False, "error": "unexpected_error", "message": str(e)}
        
    finally:
        if page:
            try: await page.close()
            except: pass
