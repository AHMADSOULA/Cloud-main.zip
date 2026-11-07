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

async def run_sso_flow(context, bot, chat_id, sso_url: str, image: str, status_msg=None) -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    region = "us-central1" if _has_password(sso_url) else "europe-west1"
    
    console = CloudConsole(context, bot, chat_id)
    page = None

    async def update_status(step, text=""):
        if status_msg:
            try: await status_msg.edit_text(f"⏳ جاري التنفيذ... [{step}/6] {text}")
            except: pass

    try:
        page = await context.new_page()
        
        # 1. فتح الرابط
        await update_status(1, "فتح الرابط")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2. TOS
        await update_status(2, "قبول التوجيهات")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

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
        await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)

        # 6. Get URL
        await update_status(6, "انتظار الرابط")
        final_url = await console.step5_get_deployed_url(page)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        log.error(f"❌ فشل في الخطوة: {e}")
        # ✅ التصوير كيوقع هنا فقط (عند الخطأ)
        if page and not page.is_closed():
            try: await console._shot(page)
            except: pass
        return {"success": False, "error": "service_failed", "message": str(e)}
    finally:
        if page:
            try: await page.close()
            except: pass
