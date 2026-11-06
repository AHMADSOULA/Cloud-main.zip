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
        if "accountdeleted" in url or "deletedaccount" in url: return "account_deleted"
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
            # التصوير عند الخطأ
            if page and not page.is_closed():
                await console._shot(page, "📸 تفاصيل الخطأ:")
            return {"success": False, "error": err_code, "message": extra_msg}

        # 1
        await update_status(1, "فتح الرابط")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        await page.wait_for_timeout(2000)
        await console._shot(page, "📸 خطوة 1: فتح الرابط") # ✅ تصوير
        
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        # 2
        await update_status(2, "قبول التوجيهات")
        try: await console.step1_welcome_screen(page)
        except: pass
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except: pass
        await page.wait_for_timeout(3000)
        await console._shot(page, "📸 خطوة 2: بعد الدخول للحساب") # ✅ تصوير
        
        blocked = await _is_blocked(page)
        if blocked: return await handle_error(blocked)

        # 3
        await update_status(3, "قبول الشروط")
        try: await console.step2_terms_dialog(page)
        except: pass
        await page.wait_for_timeout(2000)
        await console._shot(page, "📸 خطوة 3: بعد قبول الشروط") # ✅ تصوير

        authuser = extract_authuser(page.url)

        # 4
        await update_status(4, "تفعيل API")
        try: 
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                return await handle_error("browser_crashed", "❌ المتصفح طاح.")
        await page.wait_for_timeout(2000)
        await console._shot(page, "📸 خطوة 4: تفعيل API") # ✅ تصوير

        # 5
        await update_status(5, "إنشاء الخدمة")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            err_str = str(e)
            if "Target page, context or browser has been closed" in err_str:
                return await handle_error("browser_crashed", "❌ المتصفح طاح.")
            elif "service_already_exists" in err_str:
                return await handle_error("service_already_exists", "❌ يوجد خدمة تعمل بنفس الاسم.")
            else:
                return await handle_error("step4_failed", err_str)
        await console._shot(page, "📸 خطوة 5: إنشاء الخدمة") # ✅ تصوير

        # 6
        await update_status(6, "انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            err_str = str(e)
            if "service_already_exists" in err_str:
                return await handle_error("service_already_exists", "❌ يوجد خدمة تعمل بنفس الاسم.")
            elif "deployment_failed" in err_str:
                return await handle_error("deployment_failed", "❌ فشل النشر.")
            elif "timeout_waiting_for_url" in err_str:
                return await handle_error("timeout_waiting_for_url", "❌ انتهى وقت الانتظار.")
            else:
                return await handle_error("step5_failed", err_str)
        await console._shot(page, "📸 خطوة 6: النجاح") # ✅ تصوير

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
