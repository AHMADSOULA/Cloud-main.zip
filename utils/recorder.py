import os
import asyncio
import io
from datetime import datetime
from utils.logger import get_logger

log = get_logger("Recorder")


class BrowserRecorder:
    def __init__(self, context=None, log_dir: str = "/tmp/recordings"):
        self.context = context
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.trace_active = False
        self.video_process = None
        self.video_path = None
        self.trace_path = None
        self.start_time = None
        self.bot = None
        self.chat_id = None

    def set_context(self, context):
        self.context = context

    def set_bot(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id

    async def start(self):
        try:
            self.start_time = datetime.now()
            if self.context:
                await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
                self.trace_active = True

            self.video_path = os.path.join(self.log_dir, f"screen_{int(asyncio.get_event_loop().time()*1000)}.mp4")
            try:
                self.video_process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    "-f", "x11grab",
                    "-video_size", "1280x720",
                    "-framerate", "10",
                    "-i", ":99.0",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "30",
                    self.video_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except Exception as e:
                log.warning(f"⚠️ ffmpeg: {e}")

            return True
        except Exception as e:
            log.error(f"❌ start: {e}")
            return False

    async def stop(self):
        try:
            if self.trace_active and self.context:
                self.trace_path = os.path.join(self.log_dir, f"trace_{int(asyncio.get_event_loop().time()*1000)}.zip")
                await self.context.tracing.stop(path=self.trace_path)
                self.trace_active = False

            if self.video_process:
                self.video_process.terminate()
                try:
                    await asyncio.wait_for(self.video_process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self.video_process.kill()

            return {"trace": self.trace_path, "video": self.video_path}
        except Exception as e:
            log.error(f"❌ stop: {e}")
            return {}

    async def send_report(self):
        if not self.bot or not self.chat_id:
            return
        try:
            duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
            lines = [f"📊 Report", f"⏱️ Duration: {int(duration)}s"]
            report_text = "\n".join(lines)
            bio = io.BytesIO(report_text.encode("utf-8"))
            bio.name = "recording_info.txt"
            bio.seek(0)
            await self.bot.send_document(chat_id=self.chat_id, document=bio, filename="recording_info.txt")

            if self.trace_path and os.path.exists(self.trace_path):
                with open(self.trace_path, "rb") as f:
                    await self.bot.send_document(chat_id=self.chat_id, document=f, filename=os.path.basename(self.trace_path))

            if self.video_path and os.path.exists(self.video_path):
                size_mb = os.path.getsize(self.video_path) / (1024 * 1024)
                if size_mb < 50:
                    with open(self.video_path, "rb") as f:
                        await self.bot.send_video(chat_id=self.chat_id, video=f, caption=f"🎥 ({size_mb:.1f}MB)")
        except Exception as e:
            log.error(f"❌ send_report: {e}")
