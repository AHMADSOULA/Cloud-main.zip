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

async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "invalid_link", "message": "❌ Project ID ماكانش في الرابط."}

    region = "us-central1" if "password=" in sso_url.lower() else "europe-west1"
    flag = "🇺🇸" if region == "us-central1" else "🇧🇪"

    console = CloudConsole(context, sender=sender, user_tag=user_tag)
    status_msg = await sender.reply_text("⏳ جاري التنفيذ... [0/6]") if sender else None

    async def update_status(step, text=""):
        if status_msg:
            try: await status_msg.edit_text(f"⏳ جاري التنفيذ... [{step}/6] {text}")
            except: pass

    page = None
    try:
        page = await context.new_page()
        
        async def handle_error(err_code, extra_msg=""):
            if status_msg:
                try: await status_msg.delete()
                except: pass
            if page and not page.is_closed():
                await console._shot(page, "📸 تفاصيل الخطأ:")
            return {"success": False, "error": err_code, "message": extra_msg}

        # 1. فتح الرابط
        await update_status(1, "فتح الرابط")
        try: 
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except:
            await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2. خطوة TOS الأولى
        await update_status(2, "قبول التوجيهات")
        await console.step1_welcome_screen(page)
        
        # ✅ الانتظار بحال GC.py
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 3. خطوة الشروط
        await update_status(3, "قبول الشروط")
        await console.step2_tos_and_country(page)

        # 4. خطوة تفعيل API
        await update_status(4, "تفعيل API")
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            return await handle_error("step3_failed", str(e))

        # 5. خطوة إنشاء Cloud Run
        await update_status(5, "إنشاء الخدمة")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            return await handle_error("step4_failed", str(e))

        # 6. انتظار الرابط
        await update_status(6, "انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            return await handle_error("step5_failed", str(e))

        if status_msg:
            try: await status_msg.delete()
            except: pass

        return {"success": True, "project_id": project_id, "authuser": authuser, "final_url": final_url, "domain": domain, "region": region, "flag": flag}

    except Exception as e:
        log.error(f"❌ خطأ فجائي: {e}")
        if status_msg:
            try: await status_msg.delete()
            except: pass
        if page and not page.is_closed():
            try: await console._shot(page, "📸 تفاصيل الخطأ:")
            except: pass
        return {"success": False, "error": "unexpected_error", "message": str(e)}
    finally:
        if page:
            try: await page.close()
            except: pass
