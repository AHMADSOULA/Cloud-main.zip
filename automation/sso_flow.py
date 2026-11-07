import re
import asyncio
import os
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

async def run_sso_flow(context, bot, chat_id, sso_url: str, password=None):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    console = CloudConsole(context)
    page = None

    async def send_step_photo(page, step_name):
        if not page or page.is_closed(): return
        try:
            path = f"/tmp/step_{int(asyncio.get_event_loop().time()*1000)}.jpg"
            await page.screenshot(path=path, full_page=False, type="jpeg", quality=60, timeout=5000)
            with open(path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=f"📸 الخطوة {step_name}")
            os.remove(path)
        except Exception as e:
            log.warning(f"⚠️ فشل التصوير: {e}")

    try:
        page = await context.new_page()
        
        # 1. فتح الرابط
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        await send_step_photo(page, "1: فتح الرابط")
        
        # 2. الباسورد
        await page.wait_for_timeout(2000)
        try:
            password_input = page.locator('input[type="password"]').first
            if await password_input.is_visible(timeout=2000):
                if not password:
                    return {"success": False, "error": "need_password"}
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
        except Exception as e:
            log.info(f"تجاوز الباسورد: {e}")

        # 3. التوجيهات والداشبورد
        await console.step1_welcome_screen(page)
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=30000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")
        
        await send_step_photo(page, "2: تسجيل الدخول")
        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 4. الشروط
        await console.step2_tos_and_country(page)
        await send_step_photo(page, "3: قبول الشروط")

        # 5. تفعيل API (✅ كنمسكو الصفحة الجديدة)
        page = await console.step3_enable_api(page, project_id, authuser)
        await send_step_photo(page, "4: تفعيل API")

        # 6. إنشاء الخدمة (✅ كنمسكو الصفحة الجديدة)
        page = await console.step4_create_cloud_run(page, project_id, authuser, "docker.io/ajndjd2/ahmed-vip1")
        await send_step_photo(page, "5: إنشاء الخدمة")

        # 7. الرابط
        final_url = await console.step5_get_deployed_url(page)
        domain = extract_domain_from_service_url(final_url)
        await send_step_photo(page, "6: نجاح")

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        if page and not page.is_closed():
            await send_step_photo(page, f"❌ فشل: {err_str[:50]}")
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
