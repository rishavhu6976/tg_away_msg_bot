# ============================================================
#  controlbot.py  —  User control panel (multi-user aware)
# ============================================================

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telethon.errors import PhoneCodeInvalidError, PhoneCodeExpiredError

import config
import database as db
import userbot
import admin as adm

logger = logging.getLogger(__name__)

WAIT_PHONE   = 0
WAIT_OTP     = 1
WAIT_2FA     = 2
WAIT_NEW_MSG = 3


# ── User registration ─────────────────────────────────────

async def _register_user(update: Update):
    u = update.effective_user
    s = await db.get_settings(u.id)
    await db.upsert_settings(
        u.id,
        username=u.username or "",
        full_name=u.full_name or "",
        phone=s.get("phone", ""),
        enabled=s.get("enabled", 0),
        message=s.get("message", ""),
        logged_in=s.get("logged_in", 0),
    )


# ── Dashboard ─────────────────────────────────────────────

def _dashboard_keyboard(enabled: bool, logged_in: bool, is_admin: bool):
    toggle_label = "🔴 Turn OFF Auto-Reply" if enabled else "🟢 Turn ON Auto-Reply"
    rows = []
    if logged_in:
        rows.append([InlineKeyboardButton(toggle_label,          callback_data="toggle")])
        rows.append([InlineKeyboardButton("✏️ Change Message",   callback_data="changemsg")])
        rows.append([InlineKeyboardButton("👁 Preview Message",  callback_data="preview")])
        rows.append([InlineKeyboardButton("🚪 Logout",           callback_data="logout")])
    else:
        rows.append([InlineKeyboardButton("🔑 Login to Your Account", callback_data="login")])
    if is_admin:
        rows.append([InlineKeyboardButton("🛡️ Admin Panel",      callback_data="open_admin")])
    return InlineKeyboardMarkup(rows)


async def _show_dashboard(reply_fn, user_id: int):
    s         = await db.get_settings(user_id)
    enabled   = bool(s["enabled"])
    logged_in = bool(s["logged_in"])
    is_admin  = adm.is_admin(user_id)

    if logged_in:
        status_line = (
            f"{'🟢 Auto-Reply: **ON**' if enabled else '🔴 Auto-Reply: **OFF**'}\n"
            f"📝 Message set: {'Yes ✅' if s['message'] else 'No ❌'}\n"
        )
    else:
        status_line = "🔒 Not logged in yet.\n"

    admin_line = "\n🛡️ _You have admin access._" if is_admin else ""

    await reply_fn(
        "╔══════════════════════════╗\n"
        "║  🤖  Auto-Reply Userbot  ║\n"
        "╚══════════════════════════╝\n\n"
        + status_line + admin_line + "\n\nUse the buttons below:",
        reply_markup=_dashboard_keyboard(enabled, logged_in, is_admin),
        parse_mode="Markdown",
    )


# ── /start ────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _register_user(update)
    await _show_dashboard(update.message.reply_text, update.effective_user.id)


# ── Button handler ────────────────────────────────────────

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    user_id = query.from_user.id

    if data.startswith("adm_"):
        await adm.admin_button(update, ctx)
        return

    if data == "open_admin":
        if not adm.is_admin(user_id):
            await query.message.reply_text("⛔ Admin access only.")
            return
        stats = await db.count_users()
        await query.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║  🛡️  Admin Control Panel     ║\n"
            "╚══════════════════════════════╝\n\n"
            f"👥 Total users   : `{stats['total']}`\n"
            f"🔑 Logged-in     : `{stats['active']}`\n"
            f"🟢 Auto-reply ON : `{stats['enabled']}`",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👥 All Users",     callback_data="adm_users"),
                    InlineKeyboardButton("🔑 Logged-In",     callback_data="adm_loggedin"),
                ],
                [
                    InlineKeyboardButton("📋 User Messages", callback_data="adm_messages"),
                    InlineKeyboardButton("📡 Broadcast",     callback_data="adm_broadcast"),
                ],
                [
                    InlineKeyboardButton("📜 Broadcast Log", callback_data="adm_bcastlog"),
                    InlineKeyboardButton("🚫 Force Logout",  callback_data="adm_kick"),
                ],
            ]),
            parse_mode="Markdown",
        )
        return

    if data == "toggle":
        current = await db.is_enabled(user_id)
        await db.set_enabled(user_id, not current)
        state = "🟢 ON" if not current else "🔴 OFF"
        await query.edit_message_text(
            f"Auto-reply is now **{state}**.", parse_mode="Markdown"
        )
        await _show_dashboard(query.message.reply_text, user_id)

    elif data == "preview":
        msg = await db.get_message(user_id)
        await query.message.reply_text(
            f"📋 **Your auto-reply message:**\n\n{msg or '_Not set yet._'}",
            parse_mode="Markdown",
        )

    elif data == "changemsg":
        await query.message.reply_text(
            "✏️ Send your new auto-reply message.\nType /cancel to abort."
        )
        ctx.user_data["state"] = WAIT_NEW_MSG

    elif data == "login":
        await query.message.reply_text(
            "📱 Send your phone number in international format.\n"
            "Example: `+919876543210`\n\nType /cancel to abort.",
            parse_mode="Markdown",
        )
        ctx.user_data["state"] = WAIT_PHONE

    elif data == "logout":
        await userbot.logout(user_id)           # ← scoped to this user
        await db.set_logged_in(user_id, False)
        await db.set_enabled(user_id, False)
        await query.edit_message_text("✅ Logged out successfully.")
        await _show_dashboard(query.message.reply_text, user_id)


# ── Commands ──────────────────────────────────────────────

async def cmd_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _register_user(update)
    await update.message.reply_text(
        "📱 Send your phone number in international format.\n"
        "Example: `+919876543210`\n\nType /cancel to abort.",
        parse_mode="Markdown",
    )
    ctx.user_data["state"] = WAIT_PHONE


async def cmd_logout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await userbot.logout(uid)
    await db.set_logged_in(uid, False)
    await db.set_enabled(uid, False)
    await update.message.reply_text("✅ Logged out successfully.")


async def cmd_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_logged_in(uid):
        await update.message.reply_text("❌ Not logged in. Use /login first.")
        return
    current = await db.is_enabled(uid)
    await db.set_enabled(uid, not current)
    state = "🟢 ON" if not current else "🔴 OFF"
    await update.message.reply_text(
        f"Auto-reply is now **{state}**.", parse_mode="Markdown"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _register_user(update)
    await _show_dashboard(update.message.reply_text, update.effective_user.id)


async def cmd_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await db.get_message(update.effective_user.id)
    await update.message.reply_text(
        f"📋 **Your auto-reply:**\n\n{msg or '_Not set yet._'}",
        parse_mode="Markdown",
    )


async def cmd_setmsg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✏️ Send your new auto-reply message.\nType /cancel to abort."
    )
    ctx.user_data["state"] = WAIT_NEW_MSG


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("state",     None)
    ctx.user_data.pop("adm_state", None)
    await update.message.reply_text("❌ Cancelled.")


# ── Message router ────────────────────────────────────────

async def message_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    # Let admin flow intercept first
    if adm.is_admin(user_id):
        if await adm.admin_message_router(update, ctx):
            return

    state = ctx.user_data.get("state")

    # ── Phone number ───────────────────────────────────────
    if state == WAIT_PHONE:
        await update.message.reply_text("⏳ Sending OTP…")
        try:
            await userbot.send_code(user_id, text)   # ← scoped to user
            ctx.user_data["state"] = WAIT_OTP
            await update.message.reply_text(
                "📨 OTP sent! Enter the code you received.\n"
                "Format: `1 2 3 4 5` or `12345`",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}\n\nTry /login again.")
            ctx.user_data.pop("state", None)
        return

    # ── OTP code ───────────────────────────────────────────
    if state == WAIT_OTP:
        try:
            result = await userbot.sign_in_with_code(user_id, text)
            if result == "ok":
                await _finish_login(update, ctx, user_id)
            elif result == "2fa_needed":
                ctx.user_data["state"] = WAIT_2FA
                await update.message.reply_text(
                    "🔐 2FA is enabled. Enter your Telegram password:"
                )
        except PhoneCodeInvalidError:
            await update.message.reply_text("❌ Invalid code. Try again or /cancel.")
        except PhoneCodeExpiredError:
            await update.message.reply_text("❌ Code expired. Use /login to restart.")
            ctx.user_data.pop("state", None)
        return

    # ── 2FA password ───────────────────────────────────────
    if state == WAIT_2FA:
        try:
            await userbot.sign_in_with_2fa(user_id, text)
            await _finish_login(update, ctx, user_id)
        except Exception as e:
            await update.message.reply_text(f"❌ Wrong password: {e}")
        return

    # ── New auto-reply message ─────────────────────────────
    if state == WAIT_NEW_MSG:
        await db.set_message(user_id, text)
        ctx.user_data.pop("state", None)
        await update.message.reply_text(
            f"✅ Auto-reply updated!\n\n📋 **New message:**\n{text}",
            parse_mode="Markdown",
        )
        return

    await _show_dashboard(update.message.reply_text, user_id)


async def _finish_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user_id: int):
    await db.upsert_settings(user_id, logged_in=1)
    if not await db.get_message(user_id):
        await db.set_message(user_id, config.DEFAULT_MESSAGE)
    ctx.user_data.clear()
    await update.message.reply_text(
        "✅ **Logged in successfully!**\n\n"
        "Your personal userbot is now active.\n"
        "Use the dashboard to enable auto-reply. 👇",
        parse_mode="Markdown",
    )
    await _show_dashboard(update.message.reply_text, user_id)


# ── Build Application ─────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("login",   cmd_login))
    app.add_handler(CommandHandler("logout",  cmd_logout))
    app.add_handler(CommandHandler("toggle",  cmd_toggle))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("setmsg",  cmd_setmsg))
    app.add_handler(CommandHandler("cancel",  cmd_cancel))

    adm.register(app)

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    return app
