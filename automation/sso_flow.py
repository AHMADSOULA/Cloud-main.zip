"""
automation/sso_flow.py
تنسيق العملية — صامت (بلا رسائل للخطوات)
"""
import re
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


async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    project_id = extract_project_id(sso_url)
    if not project_id:
        raise RuntimeError("❌ Project ID ماكانش في الرابط.")

    log.info(f"🚀 SSO flow — project={project_id}")

    console = CloudConsole(context, sender=sender, user_tag=user_tag)

    # ═══════ صفحة 1: TOS + Terms Dialog ═══════
    page = await context.new_page()
    try:
        await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        await console.step1_welcome_screen(page)
        await page.wait_for_timeout(2000)
        await console.step2_terms_dialog(page)

        try:
            await page.wait_for_url("**/home/dashboard**", timeout=60000)
        except Exception:
            pass

        authuser = extract_authuser(page.url)
        log.info(f"🔑 authuser = {authuser}")
    finally:
        try:
            await page.close()
        except Exception:
            pass

    # ═══════ صفحة 2: Enable API ═══════
    page = await context.new_page()
    try:
        await console.step3_enable_api(page, project_id, authuser)
    finally:
        try:
            await page.close()
        except Exception:
            pass

    # ═══════ صفحة 3: Create Cloud Run ═══════
    page = await context.new_page()
    try:
        await console.step4_create_cloud_run(page, project_id, authuser, image)
        final_url = await console.step5_get_deployed_url(page)
    finally:
        try:
            await page.close()
        except Exception:
            pass

    domain = extract_domain_from_service_url(final_url)

    return {
        "project_id": project_id,
        "authuser": authuser,
        "final_url": final_url,
        "domain": domain,
    }
