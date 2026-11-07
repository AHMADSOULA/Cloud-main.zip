"""
automation/sso_flow.py
تنسيق العملية — رسالة وحدة تتغير + region تلقائي
"""
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
    except Exception:
        return '1'


def extract_email_from_url(url: str) -> str:
    try:
        m = re.search(r'Email%3D([^%&]+%40qwiklabs\.net)', url or "")
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
        m = re.search(r'Email=([^&\s#]+@qwiklabs\.net)', url or "")
        if m:
            return m.group(1)
        m = re.search(r'([a-zA-Z0-9\.\-]+@qwiklabs\.net)', url or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def extract_password_from_url(url: str) -> str:
    try:
        m = re.search(r'Password=([^&\s#]+)', url or "")
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
    except Exception:
        pass
    return None


def _has_password(url: str) -> bool:
    return "password=" in (url or "").lower()


async def _is_dashboard(page) -> bool:
    try:
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                if (url.includes('console.cloud.google.com') &&
                    !url.includes('signin') &&
                    !url.includes('accounts.google.com')) {
                    const body = (document.body.innerText || '').toLowerCase();
                    if (body.includes('sign in') && body.includes('google account')) return false;
                    if (body.includes('account deleted')) return false;
                    return true;
                }
                return false;
            }
        """)
    except Exception:
        return False


async def _is_blocked(page) -> str:
    try:
        return await page.evaluate("""
            () => {
                const url = window.location.href.toLowerCase();
                const body = (document.body.innerText || '').toLowerCase();

                if (body.includes('account deleted') ||
                    body.includes('account has been deleted') ||
                    body.includes('this account was recently deleted')) {
                    return 'account_deleted';
                }

                if (url.includes('accounts.google.com/signin') && !url.includes('addsession')) {
                    return 'signin';
                }

                if (body.includes('session expired') ||
                    body.includes('no longer valid') ||
                    body.includes('invalid link') ||
                    body.includes('sign in to continue') ||
                    body.includes('link you followed has expired')) {
                    return 'expired';
                }

                return null;
            }
        """)
    except Exception:
        return None


async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        raise RuntimeError("❌ Project ID ماكانش في الرابط.")

    if _has_password(sso_url):
        region = "us-central1"
        flag = "🇺🇸"
        log.info("🇺🇸 Region = US")
    else:
        region = "europe-west1"
        flag = "🇧🇪"
        log.info("🇧🇪 Region = EU")

    log.info(f"🚀 SSO — project={project_id}")

    console = CloudConsole(context, sender=sender, user_tag=user_tag)

    status_msg = None
    if sender:
        try:
            status_msg = await sender.reply_text("🚀 جاري التنفيذ... [0/8]")
        except Exception:
            status_msg = None

    async def update_status(step, text=""):
        if not status_msg:
            return
        try:
            await status_msg.edit_text(f"🚀 جاري التنفيذ... [{step}/8] {text}")
        except Exception:
            pass

    page = await context.new_page()
    try:
        # 1
        await update_status(1, "فتح الرابط")
        try:
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            await page.goto(sso_url, wait_until="commit", timeout=60000)

        await page.wait_for_timeout(2500)

        blocked = await _is_blocked(page)
        if blocked:
            log.warning(f"❌ {blocked}")
            await console._shot(page, f"❌ {blocked}")
            messages_map = {
                "account_deleted": "❌ الحساب محذوف — SSO منتهي",
                "signin": "❌ رجعنا لصفحة تسجيل الدخول — SSO منتهي",
                "expired": "❌ الرابط منتهي",
            }
            return {"success": False, "error": blocked, "message": messages_map.get(blocked, "❌ SSO منتهي")}

        # 2
        await update_status(2, "TOS")
        try:
            await console.step1_welcome_screen(page)
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

        await page.wait_for_timeout(1500)

        blocked = await _is_blocked(page)
        if blocked:
            log.warning(f"❌ {blocked} بعد TOS")
            await console._shot(page, f"❌ {blocked}")
            return {"success": False, "error": blocked, "message": "❌ SSO منتهي بعد TOS"}

        # 3
        await update_status(3, "Terms Dialog")
        try:
            await console.step2_terms_dialog(page)
        except Exception as e:
            log.warning(f"⚠️ step2: {e}")

        await page.wait_for_timeout(1500)

        # 4
        log.info("⏳ نستناو Dashboard...")
        dashboard_ok = False
        for i in range(20):
            await page.wait_for_timeout(1000)
            blocked = await _is_blocked(page)
            if blocked:
                log.warning(f"❌ {blocked} بعد {i+1}s")
                await console._shot(page, f"❌ {blocked}")
                messages_map = {
                    "account_deleted": "❌ الحساب محذوف — SSO منتهي",
                    "signin": "❌ SSO منتهي — رجعنا لصفحة تسجيل الدخول",
                    "expired": "❌ الرابط منتهي",
                }
                return {"success": False, "error": blocked, "message": messages_map.get(blocked, "❌ SSO منتهي")}

            if await _is_dashboard(page):
                dashboard_ok = True
                log.info(f"✅ Dashboard بعد {i+1}s")
                break

        if not dashboard_ok:
            await console._shot(page, "❌ ما وصلناش Dashboard")
            return {"success": False, "error": "no_dashboard", "message": "❌ ما وصلناش Dashboard"}

        authuser = extract_authuser(page.url)
        log.info(f"🔑 authuser = {authuser}")

        # 5
        await update_status(4, "تفعيل API")
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception as e:
            log.warning(f"⚠️ step3: {e}")

        # 6
        await update_status(5, f"إنشاء Cloud Run {flag}")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            await console._shot(page, "❌ step4 فشل")
            return {"success": False, "error": "step4_failed", "message": str(e)[:200]}

        # 7
        await update_status(7, "Create")
        await page.wait_for_timeout(400)

        # 8
        await update_status(8, "انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            await console._shot(page, "❌ step5 فشل")
            return {"success": False, "error": "step5_failed", "message": str(e)[:200]}

        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

    finally:
        try:
            await page.close()
        except Exception:
            pass

    return {
        "success": True,
        "project_id": project_id,
        "authuser": authuser,
        "final_url": final_url,
        "domain": domain,
        "region": region,
        "flag": flag,
    }
