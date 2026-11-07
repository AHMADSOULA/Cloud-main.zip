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

async def run_sso_flow(context, bot, chat_id, sso_url: str, status_msg, image_uri="docker.io/ajndjd2/ahmed-vip1"):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "PROJECT_ID_MISSING"}

    console = CloudConsole(context)
    page = None
    start_time = time.time()
    
    steps = [
        "فتح رابط",
        "تسجيل دخول",
        "موافقت على شروط",
        "cloud run api",
        "تعبئة حقول",
        "crater",
        "انتضار رابط run.app"
    ]
    
    async def update_msg(step_idx, status="loading"):
        lines = ["⏳ جاري التنفيذ...\n"]
        for i, s in enumerate(steps):
            if i < step_idx:
                lines.append(f"{s} ✅")
            elif i == step_idx:
                if status == "loading":
                    lines.append(f"{s} ...")
                elif status == "success":
                    lines.append(f"{s} ✅")
                elif status == "error":
                    lines.append(f"{s} ❌")
        text = "\n".join(lines)
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    try:
        page = await context.new_page()
        
        # 1. فتح رابط (نفس GC.py)
        await update_msg(0, "loading")
        try:
            await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            await page.goto(sso_url, wait_until="commit", timeout=60000)
        await update_msg(0, "success")
        
        # 2. تسجيل دخول (فحص متزامن وسريع)
        await update_msg(1, "loading")
        await console.step1_welcome_screen(page)
        
        try:
            # ننتظر أيهما يظهر أولاً: الداشبورد أو رسالة الحساب المحذوف (أقصى وقت 45 ثانية)
            dashboard_task = asyncio.create_task(page.wait_for_url("**/home/dashboard**", timeout=45000))
            deleted_task = asyncio.create_task(page.get_by_text("Account deleted").wait_for(state="visible", timeout=45000))
            
            done, pending = await asyncio.wait([dashboard_task, deleted_task], return_when=asyncio.FIRST_COMPLETED)
            
            for task in pending:
                task.cancel()
                
            if deleted_task in done and not deleted_task.cancelled():
                raise Exception("EXPIRED_LINK")
            
            await update_msg(1, "success")
            
        except Exception as e:
            await update_msg(1, "error")
            if "EXPIRED_LINK" in str(e):
                raise e
            raise Exception("EXPIRED_LINK")
            
        current_qs = parse_qs(urlparse(page.url).query)
        authuser = current_qs.get('authuser', ['1'])[0]
        
        # 3. موافقة شروط
        await update_msg(2, "loading")
        await console.step2_tos_and_country(page)
        await update_msg(2, "success")
        
        # 4. تفعيل API
        await update_msg(3, "loading")
        await console.step3_enable_api(page, project_id, authuser)
        await update_msg(3, "success")
        
        # 5 & 6. تعبئة حقول و Crater
        await update_msg(4, "loading")
        await console.step4_create_cloud_run(page, project_id, authuser, image_uri)
        await update_msg(4, "success")
        await update_msg(5, "success")
        
        # 7. انتظار الرابط
        await update_msg(6, "loading")
        final_url = await console.step5_get_deployed_url(page)
        await update_msg(6, "success")
        
        domain = extract_domain_from_service_url(final_url)
        elapsed_time = int(time.time() - start_time)
        
        region = "us-central1"
        if "-" in domain:
            parts = domain.split("-")
            if len(parts) > 2: 
                region = f"{parts[-2]}-{parts[-1]}"
                
        return {"success": True, "domain": domain, "region": region, "time_taken": elapsed_time}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        
        if "EXPIRED_LINK" in err_str:
            return {"success": False, "error": "EXPIRED_LINK"}
        elif "SERVICE_EXISTS" in err_str:
            return {"success": False, "error": "SERVICE_EXISTS"}
        elif "TIMEOUT_URL" in err_str:
            return {"success": False, "error": "SERVICE_EXISTS"}
        else:
            return {"success": False, "error": "UNKNOWN"}
    finally:
        if page:
            try: await page.close()
            except: pass
