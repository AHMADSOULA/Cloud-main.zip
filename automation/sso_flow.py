import re
import asyncio
import os
from urllib.parse import urlparse
from automation.console import CloudConsole
from automation.api_deployer import deploy_cloud_run
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

async def run_sso_flow(context, bot, chat_id, sso_url: str, status_msg=None, password=None):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    console = CloudConsole(context)
    page = None
    access_token = None

    async def update_msg(text):
        if status_msg:
            try: await status_msg.edit_text(text)
            except: pass

    # ✅ التقاط التوكن من الشبكة
    def handle_request(request):
        nonlocal access_token
        if access_token: return
        if "googleapis.com" in request.url or "console.cloud.google.com" in request.url:
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if auth and auth.startswith("Bearer "):
                access_token = auth.replace("Bearer ", "").strip()
                log.info("✅ تم التقاط الـ Token من الشبكة!")

    try:
        page = await context.new_page()
        page.on("request", handle_request) # ✅ كنبداو نسمعو من اللول
        
        # 1. الدخول
        await update_msg("1) فتح رابط الطالب...")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2. الباسورد
        await update_msg("2) جاري تسجيل الدخول...")
        await page.wait_for_timeout(3000)
        try:
            password_input = page.locator('input[type="password"]').first
            if await password_input.is_visible(timeout=3000):
                if not password:
                    return {"success": False, "error": "need_password"}
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
        except Exception as e:
            log.info(f"تجاوز الباسورد: {e}")

        # 3. التوجيهات
        await update_msg("3) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")

        # 4. الشروط
        await update_msg("4) قبول الشروط...")
        await console.step2_tos_and_country(page)

        # 5. استخراج التوكن (محاولة قوية)
        await update_msg("5) استخراج بيانات الدخول...")
        await page.wait_for_timeout(5000) # ✅ نعطيو 5 ثواني للداشبورد باش يحمل مزيان

        if not access_token:
            # محاولة قراءة التوكن مباشرة من المتصفح
            try:
                access_token = await page.evaluate("""
                    async () => {
                        try {
                            if (window.gapi && window.gapi.auth) {
                                const auth = window.gapi.auth.getToken();
                                if (auth && auth.access_token) return auth.access_token;
                            }
                        } catch(e) {}
                        try {
                            if (window.gapi && window.gapi.auth2) {
                                const auth2 = window.gapi.auth2.getAuthInstance();
                                if (auth2 && auth2.currentUser.get()) {
                                    const auth = auth2.currentUser.get().getAuthResponse();
                                    if (auth && auth.access_token) return auth.access_token;
                                }
                            }
                        } catch(e) {}
                        return null;
                    }
                """)
            except: pass

        if not access_token:
            return {"success": False, "error": "❌ فشل استخراج Token. يرجى المحاولة مرة أخرى."}

        # 6. النشر
        await update_msg("6) جاري النشر عبر API...")
        final_url = await asyncio.to_thread(deploy_cloud_run, project_id, access_token)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        if page and not page.is_closed():
            try:
                await page.wait_for_timeout(2000)
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(path)
            except: pass
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
