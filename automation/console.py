import asyncio
from playwright.async_api import expect
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context, sender=None, user_tag=None):
        self.context = context
        self.sender = sender
        self.user_tag = user_tag or "@user"

    async def _shot(self, page, caption: str = ""):
        if not self.sender:
            return
        try:
            path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.png"
            await page.screenshot(path=path, full_page=False, timeout=8000)
            with open(path, "rb") as f:
                try:
                    # ✅ نرسلو الصورة كرسالة جديدة بوحدها
                    bot = self.sender.get_bot()
                    if caption:
                        await bot.send_photo(chat_id=self.sender.chat_id, photo=f, caption=caption[:1000])
                    else:
                        await bot.send_photo(chat_id=self.sender.chat_id, photo=f) # بلا كابسيون
                    log.info(f"📸 Screenshot sent")
                except Exception as e:
                    log.warning(f"⚠️ send_photo: {e}")
            import os
            try:
                os.remove(path)
            except Exception:
                pass
        except Exception as e:
            log.warning(f"⚠️ _shot: {e}")

    # ... (باقي الدوال بحال step1, step2, step3, step4, step5 خليهم كيف ما هو)
    # غير تأكد أنك كتستعمل النسخة الأخيرة اللي فيها خطأ service_already_exists
