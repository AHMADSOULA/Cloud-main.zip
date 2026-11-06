from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool = False):
    """القائمة الرئيسية للمستخدمين"""
    rows = [
        [InlineKeyboardButton("♠️ آخر نتيجة", callback_data="last_result"), InlineKeyboardButton("❤️ نشر جديد", callback_data="new_deploy")],
        [InlineKeyboardButton("👤 حسابي والحاويات", callback_data="my_account")],
        [InlineKeyboardButton("📊 حالتي", callback_data="status"), InlineKeyboardButton("❓ مساعدة", callback_data="help")],
    ]
    
    # ✅ نزيدو زر الأدمن غير إلا كان المستخدم هو الأدمن
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ لوحة الأدمن (ADMIN)", callback_data="admin_panel")])
        
    return InlineKeyboardMarkup(rows)


def admin_menu():
    """لوحة الأدمن: الأزرار القديمة + الأزرار الجديدة"""
    return InlineKeyboardMarkup([
        # 🔥 الأزرار الجديدة اللي طلبتيها
        [InlineKeyboardButton("👥 قائمة المستخدمين والنقاط", callback_data="admin_users")],
        [InlineKeyboardButton("💳 شحن نقاط لمستخدم (عبر ID)", callback_data="admin_send_points")],
        
        # 📌 الأزرار القديمة اللي كانت عندك (خليتها كيف ما هي)
        [InlineKeyboardButton("📊 إحصائيات بوت", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 محظورين من بوت", callback_data="admin_banned")],
        [InlineKeyboardButton("📋 قائمة طلبات استخدام", callback_data="admin_requests")],
        [InlineKeyboardButton("⚡ زيادة سرعة مستخدم", callback_data="admin_priority")],
        [InlineKeyboardButton("🔨 حضر مستخدم عبر ID", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ إعطاء صلاحية عبر ID", callback_data="admin_grant")],
        [InlineKeyboardButton("⏸️ توقيف/تشغيل مستخدم", callback_data="admin_pause")],
        [InlineKeyboardButton("📢 إرسال رسالة إلى مستخدمين", callback_data="admin_broadcast")],
        
        # ⛔ أزرار إيقاف وتشغيل البوت
        [InlineKeyboardButton("⛔ إيقاف البوت عن الجميع", callback_data="admin_stop_all")],
        [InlineKeyboardButton("▶️ تشغيل البوت للجميع", callback_data="admin_start_all")],
        
        # 🔙 زر الرجوع
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main")],
    ])


def my_account_menu():
    """قائمة إدارة الحاويات الخاصة بالمستخدم"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة حاوية Docker", callback_data="add_docker")],
        [InlineKeyboardButton("🗑️ حذف حاوية", callback_data="del_docker")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])


def containers_menu(containers):
    """قائمة الحاويات اللي كتظهر ملي يبغي ينشر المستخدم"""
    rows = []
    for c in containers:
        rows.append([InlineKeyboardButton(f"📦 {c['name']}", callback_data=f"use_docker_{c['id']}")])
    
    rows.append([InlineKeyboardButton("➕ إضافة حاوية جديدة", callback_data="add_docker")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)
