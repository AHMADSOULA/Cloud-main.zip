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

    # ✅ دالة التقاط الـ Token
    def capture_token(request):
        nonlocal access_token
        if access_token:
            return
        try:
            headers = request.headers
            auth = headers.get("authorization") or headers.get("Authorization")
            if auth and auth.startswith("Bearer "):
                access_token = auth.replace("Bearer ", "").strip()
                log.info("✅ تم التقاط الـ Token من الشبكة!")
        except Exception:
            pass

    try:
        page = await context.new_page()
        # ✅ نبداو نسمعو للطلبات من اللول
        page.on("request", capture_token)
        
        # 1. تسجيل الدخول
        await update_msg("1) فتح رابط الطالب...")
        try: 
            await page.goto(sso_url, wait_until="networkidle", timeout=60000)
        except: 
            await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        await page.wait_for_timeout(3000)
        
        try:
            password_input = page.locator('input[type="password"]').first
            if await password_input.is_visible(timeout=3000):
                if not password:
                    return {"success": False, "error": "need_password"}
                
                await update_msg("2) إدخال كلمة السر...")
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
        except Exception as e:
            log.info(f"تجاوز الباسورد: {e}")

        await update_msg("3) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")

        await update_msg("4) قبول الشروط...")
        await console.step2_tos_and_country(page)

        # ✅ نعطيو شوية وقت للداشبورد باش يصيفط طلبات الـ API ويبان الـ Token
        await update_msg("5) جاري استخراج الـ Token...")
        await page.wait_for_timeout(5000)

        # ✅ إلا ما لقيناش الـ Token من الشبكة، نجربو نجيبوه من المتصفح ديراكت
        if not access_token:
            log.info("محاولة استخراج الـ Token من داخل المتصفح...")
            try:
                access_token = await page.evaluate("""
                    () => {
                        try { return window.gapi.auth.getToken().access_token; } catch(e) {}
                        try { return window.gapi.auth2.getAuthInstance().currentUser.get().getAuthResponse().access_token; } catch(e) {}
                        return null;
                    }
                """)
            except:
                pass

        if not access_token:
            return {"success": False, "error": "❌ فشل استخراج Token. يرجى المحاولة مرة أخرى أو التأكد من الحساب."}

        # ✅ 6. النشر عبر API
        await update_msg("6) جاري النشر عبر Google API...")
        
        final_url = await asyncio.to_thread(deploy_cloud_run, project_id, access_token)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        
        if page and not page.is_closed() and "Execution context was destroyed" not in err_str:
            try:
                await page.wait_for_timeout(2000)
                path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
                await page.screenshot(path=path, full_page=True, type="jpeg", quality=60, timeout=5000)
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(path)
            except: pass
            
        if "Execution context was destroyed" in err_str:
            err_str = "❌ حدث تحويل مفاجئ في الصفحة. يرجى إعادة المحاولة."
            
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
