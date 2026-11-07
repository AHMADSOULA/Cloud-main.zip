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
        return {"success": False, "error": "❌ Project ID في الرابط."}

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
        
        # 1
        await update_status(1, "فتح الرابط")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2
        await update_status(2, "قبول التوجيهات")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 3
        await update_status(3, "قبول الشروط")
        await console.step2_tos_and_country(page)

        # 4
        await update_status(4, "تفعيل API")
        await console.step3_enable_api(page, project_id, authuser)

        # 5
        await update_status(5, "إنشاء الخدمة")
        await console.step4_create_cloud_run(page, project_id, authuser, image)

        # 6
        await update_status(6, "انتظار الرابط")
        final_url = await console.step5_get_deployed_url(page)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        log.error(f"❌ فشل في الخطوة {current_step}: {e}")
        # التصوير عند الخطأ فقط
        if page and not page.is_closed():
            try:
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                import os
                os.remove(path)
            except Exception as shot_err:
                log.error(f"فشل التصوير: {shot_err}")
        
        return {"success": False, "error": str(e)}
    finally:
        if page:
            try: await page.close()
            except: pass
