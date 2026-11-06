from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import db

def main_menu(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton("♠️ آخر نتيجة", callback_data="last_result"), InlineKeyboardButton("❤️ نشر جديد", callback_data="new_deploy")],
        [InlineKeyboardButton("👤 حسابي والحاويات", callback_data="my_account")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 إحصائيات المستخدمين", callback_data="admin_users")],
        [InlineKeyboardButton("💳 إرسال نقاط لمستخدم", callback_data="admin_send_points")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def containers_menu(containers):
    rows = []
    for c in containers:
        rows.append([InlineKeyboardButton(f"📦 {c['name']}", callback_data=f"use_docker_{c['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة حاوية جديدة", callback_data="add_docker")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

def my_account_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة حاوية", callback_data="add_docker")],
        [InlineKeyboardButton("🗑️ حذف حاوية", callback_data="del_docker")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])
