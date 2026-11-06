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

async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    region = "us-central1" if _has_password(sso_url) else "europe-west1"
    flag = "🇺🇸" if _has_password(sso_url) else "🇧🇪"

    console = CloudConsole(context, sender=sender, user_tag=user_tag)
    page = None
    try:
        page = await context.new_page()
        
        async def handle_error(err_code, extra_msg=""):
            if page:
                await console._shot(page, "") # صورة الخطأ
            return {"success": False, "error": err_code, "message": extra_msg}

        # 1-5 بلا تصوير
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)

        await page.wait_for_timeout(2000)
        
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        try: await console.step1_welcome_screen(page)
        except: pass
        await page.wait_for_timeout(1000)
        
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        try: await console.step2_terms_dialog(page)
        except: pass
        await page.wait_for_timeout(1000)

        authuser = extract_authuser(page.url)

        try: await console.step3_enable_api(page, project_id, authuser)
        except: pass

        # 6: التصوير كيبدا هنا
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            err_str = str(e)
            if "service_already_exists" in err_str:
                return await handle_error("service_already_exists")
            elif "invalid_docker_image" in err_str:
                return await handle_error("invalid_docker_image")
            elif "image_field_empty" in err_str:
                return await handle_error("image_field_empty")
            else:
                return await handle_error("step4_failed", err_str)

        # 7-8
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            err_str = str(e)
            if "service_already_exists" in err_str:
                return await handle_error("service_already_exists")
            elif "deployment_failed" in err_str:
                return await handle_error("deployment_failed")
            elif "timeout_waiting_for_url" in err_str:
                return await handle_error("timeout_waiting_for_url")
            else:
                return await handle_error("step5_failed", err_str)

        return {"success": True, "project_id": project_id, "authuser": authuser, "final_url": final_url, "domain": domain, "region": region, "flag": flag}

    except Exception as e:
        log.error(f"❌ خطأ فجائي: {e}")
        if page:
            try: await console._shot(page, "")
            except: pass
        return {"success": False, "error": "unexpected_error", "message": str(e)}
        
    finally:
        if page:
            try: await page.close()
            except: pass
