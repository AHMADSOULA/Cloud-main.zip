from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool = False):
    """القائمة الرئيسية"""
    rows = [
        [InlineKeyboardButton("📊 حالتي", callback_data="status")],
        [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ ADMIN", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def admin_menu():
    """لوحة تحكم الأدمن"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات بوت", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])
