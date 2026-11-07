from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton("📊 حالتي", callback_data="status")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ ADMIN", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات بوت", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 مستخدمين حالياً", callback_data="admin_users")],
        [InlineKeyboardButton("🚫 محظورين من بوت", callback_data="admin_banned")],
        [InlineKeyboardButton("📋 قائمة طلبات استخدام", callback_data="admin_requests")],
        [InlineKeyboardButton("⚡ زيادة سرعة مستخدم", callback_data="admin_priority")],
        [InlineKeyboardButton("🔨 حضر مستخدم عبر ID", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ إعطاء صلاحية عبر ID", callback_data="admin_grant")],
        [InlineKeyboardButton("⏸️ توقيف/تشغيل مستخدم", callback_data="admin_pause")],
        [InlineKeyboardButton("📢 إرسال رسالة إلى مستخدمين", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⛔ إيقاف البوت عن الجميع", callback_data="admin_stop_all")],
        [InlineKeyboardButton("▶️ تشغيل البوت للجميع", callback_data="admin_start_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


def list_menu(items: list, prefix: str):
    """قائمة عامة (للدول والقارات)"""
    rows = []
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            name = item.get('name', '')
            emoji = item.get('emoji', '')
            display = f"{emoji} {name}" if emoji else f"🌍 {name}"
        else:
            display = str(item)
        if len(display) > 60:
            display = display[:57] + "..."
        rows.append([InlineKeyboardButton(display, callback_data=f"{prefix}:{idx}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)
