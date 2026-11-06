from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(is_admin: bool = False):
    rows = []
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ ADMIN", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات بوت", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])
