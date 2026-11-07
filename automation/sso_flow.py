import re
import asyncio
import os
import time
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

async def run_sso_flow(context, bot, chat_id, sso_url: str, status_msg=None, password=None, image_uri=""):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID غير موجود في الرابط."}

    console = CloudConsole(context)
    page = None
    start_time = time.time()

    # قائمة لتخزين الخطوات وعرضها في رسالة واحدة
    steps_log = ["✅ تم استلام الرابط. جاري التنفيذ الآن...\n"]

    async def update_msg(new_step_text=None, replace_last=False, is_final=False):
        if replace_last and len(steps_log) > 1:
            steps_log[-1] = new_step_text
        elif new_step_text:
            steps_log.append(new_step_text)
        
        full_text = "\n".join(steps_log)
        if status_msg:
            try: 
                await status_msg.edit_text(full_text)
            except Exception: 
                pass # تجاهل خطأ عدم تغيير النص

    async def take_screenshot(caption_text):
        if not page or page.is_closed(): return
        try:
            path = f"/tmp/shot_{int(time.time()*1000)}.jpg"
            await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
            with open(path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=caption_text[:1000])
            os.remove(path)
        except Exception as e:
            log.warning(f"⚠️ فشل إرسال صورة: {e}")

    try:
        page = await context.new_page()
        
        # 1. فتح الرابط
        await update_msg("1) فتح رابط الطالب...")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # التحقق من وجود خطأ "Account deleted"
        if "Account deleted" in await page.content() or "الحساب محذوف" in await page.content():
            await update_msg("1) فتح رابط الطالب ❌", replace_last=True)
            raise Exception("Account deleted")

        # 2. الباسورد
        await update_msg("2) جاري تسجيل الدخول...")
        await page.wait_for_timeout(3000)
        try:
            password_input = page.locator('input[type="password"]').first
            if await password_input.is_visible(timeout=3000):
                if not password:
                    await update_msg("2) مطلوب كلمة السر 🔑", replace_last=True)
                    return {"success": False, "error": "need_password"}
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
            await update_msg("2 ✅", replace_last=True)
        except Exception:
            await update_msg("2 ✅", replace_last=True)

        # 3. التوجيهات والداشبورد
        await update_msg("3) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except: pass

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]
        await update_msg(f"3 ✅ (Project: {project_id})", replace_last=True)

        # 4. الشروط
        await update_msg("4) قبول الشروط...")
        await console.step2_tos_and_country(page)
        await update_msg("4 ✅", replace_last=True)

        # 5. تفعيل API
        await update_msg("5) تفعيل Cloud Run API...")
        await console.step3_enable_api(page, project_id, authuser)
        await update_msg("5 ⚠️ API مؤكد، متابعة...", replace_last=True)

        # 6. إنشاء الخدمة
        await update_msg("6) فتح Cloud Run...")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}"
        await page.goto(run_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        await update_msg("6 ✅", replace_last=True)
        
        # 7. تعبئة الحقول
        await update_msg("7) تعبئة الحقول...")
        await console.step4_create_cloud_run(page, project_id, authuser, image_uri)
        await update_msg("7 ✅", replace_last=True)

        # 8. انتظار الرابط
        await update_msg("8) انتظار رابط النشر...")
        final_url = await console.step5_get_deployed_url(page)
        await update_msg("8 ✅ Create", replace_last=True)
        
        domain = extract_domain_from_service_url(final_url)
        elapsed_time = int(time.time() - start_time)
        
        # استخراج المنطقة (الافتراضي us-central1 إذا لم نجدها)
        region = "us-central1"
        if "-" in domain:
            parts = domain.split("-")
            if len(parts) > 2: region = f"{parts[-2]}-{parts[-1]}"

        return {
            "success": True, 
            "domain": domain, 
            "region": region, 
            "time_taken": elapsed_time
        }

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        
        # تنسيق رسالة الفشل (التجمد)
        await update_msg(f"⚠️ تجمد في مرحلة unknown", is_final=True)
        if page and not page.is_closed():
            await take_screenshot(f"⚠️ تجمد في: {err_str[:100]}")
        
        return {"success": False, "error": "unknown"}
    finally:
        if page:
            try: await page.close()
            except: pass
