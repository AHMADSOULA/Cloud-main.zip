import re
import asyncio
import os

from urllib.parse import urlparse, parse_qs

from automation.console import CloudConsole
from utils.logger import get_logger

log = get_logger("SSOFlow")


def extract_project_id(url: str) -> str:
    m = re.search(
        r'(qwiklabs-gcp-[\w-]+)',
        url or ""
    )

    return m.group(1) if m else None


def extract_domain_from_service_url(service_url: str) -> str:
    s = (service_url or "").strip()

    if s.startswith("http://") or s.startswith("https://"):
        return urlparse(s).netloc.strip()

    return (
        s.replace("http://", "")
        .replace("https://", "")
        .split("/")[0]
        .strip()
    )


async def run_sso_flow(
    context,
    bot,
    chat_id,
    sso_url: str,
    status_msg=None,
    password=None
):
    project_id = extract_project_id(sso_url)

    if not project_id:
        return {
            "success": False,
            "error": "❌ Project ID في الرابط."
        }

    console = CloudConsole(context)

    page = None

    async def update_msg(text):
        if status_msg:
            try:
                await status_msg.edit_text(text)
            except:
                pass

    async def take_screenshot(caption_text):
        if not page or page.is_closed():
            return

        try:
            path = (
                f"/tmp/shot_"
                f"{int(asyncio.get_event_loop().time()*1000)}.jpg"
            )

            await page.screenshot(
                path=path,
                full_page=True,
                type="jpeg",
                quality=60,
                timeout=5000
            )

            with open(path, "rb") as f:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=caption_text[:1000]
                )

            os.remove(path)

        except Exception as e:
            log.warning(
                f"⚠️ فشل إرسال صورة: {e}"
            )

    try:
        page = await context.new_page()

        # 1. فتح الرابط
        await update_msg(
            "1) فتح رابط الطالب..."
        )

        try:
            await page.goto(
                sso_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

        except:
            await page.goto(
                sso_url,
                wait_until="commit",
                timeout=60000
            )

        # 2. الباسورد
        await update_msg(
            "2) جاري تسجيل الدخول..."
        )

        await page.wait_for_timeout(3000)

        try:
            password_input = page.locator(
                'input[type="password"]'
            ).first

            if await password_input.is_visible(timeout=3000):

                if not password:
                    return {
                        "success": False,
                        "error": "need_password"
                    }

                await password_input.fill(password)

                await page.wait_for_timeout(500)

                await page.keyboard.press("Enter")

                await page.wait_for_timeout(5000)

        except Exception as e:
            log.info(
                f"تجاوز الباسورد: {e}"
            )

        # 3. التوجيهات والداشبورد
        await update_msg(
            "3) قبول التوجيهات..."
        )

        await console.step1_welcome_screen(page)

        try:
            await page.wait_for_url(
                "**/home/dashboard**",
                timeout=45000
            )

        except Exception as e:
            log.warning(
                f"⚠️ ما وصلناش Dashboard: {e}"
            )

        current_qs = parse_qs(
            urlparse(page.url).query
        )

        authuser = current_qs.get(
            'authuser',
            ['1']
        )[0]

        # 4. الشروط
        await update_msg(
            "4) قبول الشروط..."
        )

        await console.step2_tos_and_country(page)

        # 5. تفعيل API
        await update_msg(
            "5) تفعيل Cloud Run API..."
        )

        await console.step3_enable_api(
            page,
            project_id,
            authuser
        )

        # 6. إنشاء الخدمة
        await update_msg(
            "6) إنشاء الخدمة..."
        )

        await console.step4_create_cloud_run(
            page,
            project_id,
            authuser,
            "docker.io/ajndjd2/ahmed-vip1"
        )

        # 7. انتظار رابط النشر
        await update_msg(
            "7) انتظار رابط النشر..."
        )

        final_url = await console.step5_get_deployed_url(
            page
        )

        domain = extract_domain_from_service_url(
            final_url
        )

        return {
            "success": True,
            "domain": domain
        }

    except Exception as e:

        err_str = str(e)

        # انتهاء وقت انتظار رابط النشر
        if (
            isinstance(e, TimeoutError)
            or "deployment_timeout" in err_str
        ):

            log.warning(
                "⏰ انتهى وقت انتظار رابط النشر بدون ظهور رابط"
            )

            return {
                "success": False,
                "error": "deployment_timeout"
            }

        log.error(
            f"❌ خطأ: {err_str}"
        )

        if page and not page.is_closed():
            await take_screenshot(
                f"❌ فشل: {err_str[:200]}"
            )

        return {
            "success": False,
            "error": err_str
        }

    finally:
        if page:
            try:
                await page.close()
            except:
                pass
