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

def _has_password(url: str) -> bool:
    return "password=" in (url or "").lower()

async def run_sso_flow(context, bot, chat_id, sso_url: str, image: str) -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    region = "us-central1" if _has_password(sso_url) else "europe-west1"
    flag = "🇺🇸" if region == "us-central1" else "🇧🇪"

    console = CloudConsole(context, bot, chat_id)
    page = None

    try:
        page = await context.new_page()
        
        # 1. فتح الرابط
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2. TOS
        await console.step1_welcome_screen(page)
        
        # ✅ الانتظار بحال GC.py
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 3. Terms
        await console.step2_tos_and_country(page)

        # 4. Enable API
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            await console._shot(page, str(e))
            return {"success": False, "error": "step3_failed", "message": str(e)}

        # 5. Create Cloud Run
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            await console._shot(page, str(e))
            return {"success": False, "error": "step4_failed", "message": str(e)}

        # 6. Get URL
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            await console._shot(page, str(e))
            return {"success": False, "error": "step5_failed", "message": str(e)}

        return {"success": True, "project_id": project_id, "authuser": authuser, "final_url": final_url, "domain": domain, "region": region, "flag": flag}

    except Exception as e:
        log.error(f"❌ خطأ فجائي: {e}")
        if page and not page.is_closed():
            try: await console._shot(page, str(e))
            except: pass
        return {"success": False, "error": "unexpected_error", "message": str(e)}
    finally:
        if page:
            try: await page.close()
            except: pass
