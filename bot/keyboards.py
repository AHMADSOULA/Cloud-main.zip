from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(is_admin: bool = False):
    rows = [
        [
            InlineKeyboardButton("♠️ آخر نتيجة", callback_data="last_result"), 
            InlineKeyboardButton("❤️ نشر جديد", callback_data="new_deploy")
        ],
        [
            InlineKeyboardButton("👤 حسابي والدعوات", callback_data="my_account"), 
            InlineKeyboardButton("🖌️ صورة Docker خاصة", callback_data="my_containers")
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ لوحة الأدمن (ADMIN)", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 قائمة المستخدمين والنقاط", callback_data="admin_users")],
        [InlineKeyboardButton("💳 شحن نقاط لمستخدم (عبر ID)", callback_data="admin_send_points")],
        [InlineKeyboardButton("📊 إحصائيات بوت", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 محظورين من بوت", callback_data="admin_banned")],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main")],
    ])

def my_account_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة حاوية Docker", callback_data="add_docker")],
        [InlineKeyboardButton("🗑️ حذف حاوية", callback_data="del_docker")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def containers_menu(containers):
    rows = []
    for c in containers:
        rows.append([InlineKeyboardButton(f"📦 {c['name']}", callback_data=f"use_docker_{c['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة حاوية جديدة", callback_data="add_docker")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)
