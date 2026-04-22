# ============================================================
#  admin.py  —  Admin panel commands for the control bot
# ============================================================

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.error import Forbidden, BadRequest

import config
import database as db

logger = logging.getLogger(__name__)

# ── Conversation state ────────────────────────────────────
WAIT_BROADCAST_MSG = 10
WAIT_KICK_ID       = 11

# ── Admin guard ───────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id == config.OWNER_ID or user_id in config.ADMIN_IDS


def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_admin(uid):
            await update.effective_message.reply_text("⛔ Admin access only.")
            return ConversationHandler.END
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /admin — main admin panel ─────────────────────────────

@admin_only
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = await db.count_users()
    text = (
        "╔══════════════════════════════╗\n"
        "║  🛡️  Admin Control Panel     ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👥 Total users    : `{stats['total']}`\n"
        f"🔑 Logged-in      : `{stats['active']}`\n"
        f"🟢 Auto-reply ON  : `{stats['enabled']}`\n"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 All Users",      callback_data="adm_users"),
            InlineKeyboardButton("🔑 Logged-In",      callback_data="adm_loggedin"),
        ],
        [
            InlineKeyboardButton("📋 User Messages",  callback_data="adm_messages"),
            InlineKeyboardButton("📡 Broadcast",      callback_data="adm_broadcast"),
        ],
        [
            InlineKeyboardButton("📜 Broadcast Log",  callback_data="adm_bcastlog"),
            InlineKeyboardButton("🚫 Force Logout",   callback_data="adm_kick"),
        ],
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


# ── Inline button handler ─────────────────────────────────

@admin_only
async def admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "adm_users":
        await _show_all_users(query)

    elif data == "adm_loggedin":
        await _show_logged_in(query)

    elif data == "adm_messages":
        await _show_user_messages(query)

    elif data == "adm_broadcast":
        await query.message.reply_text(
            "📡 *Broadcast Message*\n\n"
            "Send the message you want to broadcast to ALL bot users.\n"
            "Supports plain text. Type /cancel to abort.",
            parse_mode="Markdown",
        )
        ctx.user_data["adm_state"] = WAIT_BROADCAST_MSG

    elif data == "adm_bcastlog":
        await _show_broadcast_log(query)

    elif data == "adm_kick":
        await query.message.reply_text(
            "🚫 *Force Logout*\n\n"
            "Send the *user\\_id* of the user to force-logout.\n"
            "Type /cancel to abort.",
            parse_mode="Markdown",
        )
        ctx.user_data["adm_state"] = WAIT_KICK_ID

    elif data == "adm_refresh":
        stats = await db.count_users()
        await query.edit_message_text(
            f"📊 *Stats refreshed*\n\n"
            f"👥 Total users   : `{stats['total']}`\n"
            f"🔑 Logged-in     : `{stats['active']}`\n"
            f"🟢 Auto-reply ON : `{stats['enabled']}`",
            parse_mode="Markdown",
        )


# ── Show all users ────────────────────────────────────────

async def _show_all_users(query):
    users = await db.get_all_users()
    if not users:
        await query.message.reply_text("📭 No users registered yet.")
        return

    # Send in chunks (Telegram 4096 char limit)
    chunks = []
    current = f"👥 *All Users ({len(users)} total)*\n{'─'*30}\n"

    for i, u in enumerate(users, 1):
        name     = u["full_name"] or "Unknown"
        username = f"@{u['username']}" if u["username"] else "no username"
        uid      = u["user_id"]
        status   = "🟢 ON" if u["enabled"] else "🔴 OFF"
        login    = "✅ Logged in" if u["logged_in"] else "❌ Not logged in"
        joined   = u["joined_at"][:10] if u["joined_at"] else "?"

        entry = (
            f"\n*{i}.* {name} ({username})\n"
            f"   🆔 `{uid}`\n"
            f"   {login} | {status}\n"
            f"   📅 Joined: {joined}\n"
        )

        if len(current) + len(entry) > 3800:
            chunks.append(current)
            current = entry
        else:
            current += entry

    chunks.append(current)

    for chunk in chunks:
        await query.message.reply_text(chunk, parse_mode="Markdown")


# ── Show logged-in users ──────────────────────────────────

async def _show_logged_in(query):
    users = await db.get_logged_in_users()
    if not users:
        await query.message.reply_text("📭 No users are currently logged in.")
        return

    text = f"🔑 *Logged-In Accounts ({len(users)})*\n{'─'*30}\n"
    for i, u in enumerate(users, 1):
        name     = u["full_name"] or "Unknown"
        username = f"@{u['username']}" if u["username"] else "no username"
        phone    = u["phone"] or "hidden"
        status   = "🟢 Auto-reply ON" if u["enabled"] else "🔴 Auto-reply OFF"

        text += (
            f"\n*{i}.* {name} ({username})\n"
            f"   🆔 `{u['user_id']}`\n"
            f"   📞 `{phone}`\n"
            f"   {status}\n"
        )

    await query.message.reply_text(text, parse_mode="Markdown")


# ── Show users' configured auto-reply messages ────────────

async def _show_user_messages(query):
    users = await db.get_all_users()
    if not users:
        await query.message.reply_text("📭 No users registered yet.")
        return

    text = f"📋 *User Auto-Reply Messages*\n{'─'*30}\n"
    for i, u in enumerate(users, 1):
        name    = u["full_name"] or "Unknown"
        uid     = u["user_id"]
        msg     = u["message"] if u["message"] else "_not set_"
        enabled = "🟢" if u["enabled"] else "🔴"

        text += (
            f"\n{enabled} *{i}. {name}* (`{uid}`)\n"
            f"   _{msg}_\n"
        )

        if len(text) > 3500:
            await query.message.reply_text(text, parse_mode="Markdown")
            text = ""

    if text:
        await query.message.reply_text(text, parse_mode="Markdown")


# ── Broadcast log ─────────────────────────────────────────

async def _show_broadcast_log(query):
    history = await db.get_broadcast_history(limit=10)
    if not history:
        await query.message.reply_text("📭 No broadcasts sent yet.")
        return

    text = "📜 *Recent Broadcasts*\n" + "─" * 30 + "\n"
    for b in history:
        preview = b["message"][:60] + ("…" if len(b["message"]) > 60 else "")
        text += (
            f"\n📅 {b['sent_at'][:16]}\n"
            f"👤 Admin `{b['admin_id']}`\n"
            f"📨 Sent to `{b['recipients']}` users\n"
            f"💬 _{preview}_\n"
        )
    await query.message.reply_text(text, parse_mode="Markdown")


# ── Text router for admin multi-step flows ────────────────

@admin_only
async def admin_message_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    adm_state = ctx.user_data.get("adm_state")
    if adm_state is None:
        return False   # not in an admin flow — let normal router handle it

    uid  = update.effective_user.id
    text = update.message.text.strip()

    # ── Waiting for broadcast message ──
    if adm_state == WAIT_BROADCAST_MSG:
        ctx.user_data.pop("adm_state", None)

        all_ids = await db.get_all_user_ids()
        success, failed = 0, 0

        status_msg = await update.message.reply_text(
            f"📡 Broadcasting to {len(all_ids)} users…"
        )

        broadcast_text = (
            "📢 *Message from Admin*\n\n" + text
        )

        for target_id in all_ids:
            try:
                await ctx.bot.send_message(
                    chat_id=target_id,
                    text=broadcast_text,
                    parse_mode="Markdown",
                )
                success += 1
            except (Forbidden, BadRequest):
                failed += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {target_id}: {e}")
                failed += 1
            await asyncio.sleep(0.05)   # rate-limit protection

        await db.log_broadcast(uid, text, success)
        await status_msg.edit_text(
            f"✅ *Broadcast complete!*\n\n"
            f"📨 Delivered : `{success}`\n"
            f"❌ Failed    : `{failed}`",
            parse_mode="Markdown",
        )
        return True

    # ── Waiting for user ID to force-logout ──
    if adm_state == WAIT_KICK_ID:
        ctx.user_data.pop("adm_state", None)
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Invalid ID. Must be a number.")
            return True

        target = await db.get_settings(target_id)
        if not target["logged_in"]:
            await update.message.reply_text(
                f"ℹ️ User `{target_id}` is not logged in.", parse_mode="Markdown"
            )
            return True

        await db.set_logged_in(target_id, False)
        await db.set_enabled(target_id, False)

        # Notify the user
        try:
            await ctx.bot.send_message(
                chat_id=target_id,
                text=(
                    "⚠️ *Notice*\n\n"
                    "An admin has logged you out of the Auto-Reply Userbot.\n"
                    "Use /login to reconnect."
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

        name = target["full_name"] or str(target_id)
        await update.message.reply_text(
            f"✅ *{name}* (`{target_id}`) has been force-logged out.",
            parse_mode="Markdown",
        )
        return True

    return False


# ── /stats shortcut ───────────────────────────────────────

@admin_only
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = await db.count_users()
    await update.message.reply_text(
        "📊 *Bot Statistics*\n\n"
        f"👥 Total users    : `{stats['total']}`\n"
        f"🔑 Logged-in      : `{stats['active']}`\n"
        f"🟢 Auto-reply ON  : `{stats['enabled']}`",
        parse_mode="Markdown",
    )


# ── /broadcast shortcut ───────────────────────────────────

@admin_only
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 *Broadcast*\n\nSend the message to deliver to all users.\n"
        "Type /cancel to abort.",
        parse_mode="Markdown",
    )
    ctx.user_data["adm_state"] = WAIT_BROADCAST_MSG


# ── /users shortcut ───────────────────────────────────────

@admin_only
async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = await db.get_all_users()
    if not users:
        await update.message.reply_text("📭 No users registered yet.")
        return

    chunks, current = [], f"👥 *All Users ({len(users)})*\n{'─'*30}\n"
    for i, u in enumerate(users, 1):
        name     = u["full_name"] or "Unknown"
        username = f"@{u['username']}" if u["username"] else "no username"
        login    = "✅" if u["logged_in"] else "❌"
        status   = "🟢" if u["enabled"] else "🔴"
        entry = (
            f"\n*{i}.* {name} ({username})\n"
            f"   🆔 `{u['user_id']}` | {login} logged in | {status} reply\n"
        )
        if len(current) + len(entry) > 3800:
            chunks.append(current)
            current = entry
        else:
            current += entry
    chunks.append(current)
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="Markdown")


# ── Register all admin handlers onto the app ─────────────

def register(app):
    """Call this from controlbot.build_app() to attach admin handlers."""
    app.add_handler(CommandHandler("admin",     cmd_admin))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("users",     cmd_users))
    app.add_handler(
        CallbackQueryHandler(admin_button, pattern=r"^adm_")
    )
