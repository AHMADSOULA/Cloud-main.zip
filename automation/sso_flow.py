import re
import asyncio
import os
from urllib.parse import urlparse, parse_qs, unquote
from automation.console import CloudConsole, NeedPasswordException
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

async def run_sso_flow(context, bot, chat_id, sso_url: str, image: str, msg_obj):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    console = CloudConsole(context)
    page = None
    
    async def update_msg(text):
        try:
            await msg_obj.edit_text(text)
        except:
            pass

    try:
        page = await context.new_page()
        
        # 1
        await update_msg("1) فتح رابط الطالب...")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        
        # 2
        await update_msg("2 ✅")
        await console.step1_welcome_screen(page)
        
        # ✅ فحص كلمة السر
        await console.check_password_page(page)
        
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard بـ URL: {e}")

        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]

        # 3
        await update_msg(f"3 ✅ (Project: {project_id})")
        await console.step2_tos_and_country(page)

        # 4
        await update_msg("4) تفعيل Cloud Run API...")
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except:
            pass
        
        # 5
        await update_msg("5 ⚠️ API مؤكد، متابعة...")

        # 6
        await update_msg("6) فتح Cloud Run...")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}"
        await page.goto(run_url, wait_until="domcontentloaded")
        
        # 7
        await update_msg("7 ✅")
        await page.wait_for_timeout(5000)

        # 8
        await update_msg("8) تعبئة الحقول...")
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=15000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            raise Exception(f"فشل في إدخال صورة الحاوية: {str(e)}")
        
        # 9
        await update_msg("9 ✅")
        await page.wait_for_timeout(3000)

        # 10
        await update_msg("10) الخدمة Create...")
        try:
            await page.get_by_role("radio", name="Allow public access").click()
            await page.get_by_role("radio", name="Instance-based").click()
            try: await page.get_by_role("button", name="Hide").click(timeout=2000)
            except: pass
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True)
        except Exception as e:
            raise Exception(f"فشل في ضغط Create: {str(e)}")
        
        # 11
        await update_msg("11 ✅ Create")
        
        # 12
        await update_msg("12) انتظار رابط النشر...")
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=120000) 
            final_url = await link_locator.get_attribute("href")
            domain = extract_domain_from_service_url(final_url)
            return {"success": True, "domain": domain}
        except Exception as e:
            return {"success": False, "error": f"انتهى الوقت بدون رابط"}

    except NeedPasswordException:
        return {"success": False, "error": "need_password"}
    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        if page and not page.is_closed():
            try:
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
