# ... (الفوق بحال ما هو)

async def run_sso_flow(context, sso_url: str, image: str, sender=None, user_tag="@user") -> dict:
    # ... 
    status_msg = None
    if sender:
        try:
            status_msg = await sender.reply_text("🚀 جاري التنفيذ... [0/8]")
        except Exception:
            status_msg = None

    # ...

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
            await console._shot(page, "") # ✅ صورة بلا كابسيون
            if status_msg: 
                try: await status_msg.delete()
                except: pass
            return {"success": False, "error": blocked, "message": "blocked"}

        # 2
        await update_status(2, "TOS")
        try:
            await console.step1_welcome_screen(page)
        except Exception:
            pass

        await page.wait_for_timeout(1500)

        blocked = await _is_blocked(page)
        if blocked:
            await console._shot(page, "") # ✅ صورة بلا كابسيون
            if status_msg: 
                try: await status_msg.delete()
                except: pass
            return {"success": False, "error": blocked, "message": "blocked"}

        # 3
        await update_status(3, "Terms Dialog")
        try:
            await console.step2_terms_dialog(page)
        except Exception:
            pass

        await page.wait_for_timeout(1500)

        # 4
        dashboard_ok = False
        for i in range(20):
            await page.wait_for_timeout(1000)
            blocked = await _is_blocked(page)
            if blocked:
                await console._shot(page, "") # ✅ صورة بلا كابسيون
                if status_msg: 
                    try: await status_msg.delete()
                    except: pass
                return {"success": False, "error": blocked, "message": "blocked"}

            if await _is_dashboard(page):
                dashboard_ok = True
                break

        if not dashboard_ok:
            await console._shot(page, "")
            if status_msg: 
                try: await status_msg.delete()
                except: pass
            return {"success": False, "error": "no_dashboard", "message": "❌ ما وصلناش Dashboard"}

        authuser = extract_authuser(page.url)

        # 5
        await update_status(4, "تفعيل API")
        try:
            await console.step3_enable_api(page, project_id, authuser)
        except Exception:
            pass

        # 6
        await update_status(5, f"إنشاء Cloud Run {flag}")
        try:
            await console.step4_create_cloud_run(page, project_id, authuser, image, region=region)
        except Exception as e:
            err_str = str(e)
            await console._shot(page, "") # ✅ صورة بلا كابسيون
            if status_msg: 
                try: await status_msg.delete()
                except: pass
                
            if "service_already_exists" in err_str:
                return {"success": False, "error": "service_already_exists", "message": err_str}
            else:
                return {"success": False, "error": "step4_failed", "message": err_str[:200]}

        # 7 & 8 ...
        await update_status(7, "Create")
        await page.wait_for_timeout(400)

        await update_status(8, "انتظار الرابط")
        try:
            final_url = await console.step5_get_deployed_url(page)
            domain = extract_domain_from_service_url(final_url)
        except Exception as e:
            await console._shot(page, "")
            if status_msg: 
                try: await status_msg.delete()
                except: pass
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
