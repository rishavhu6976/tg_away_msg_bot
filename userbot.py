# ============================================================
#  userbot.py  —  Multi-user Telethon manager
#
#  Auto-reply sirf tab bhejega jab:
#    1. User 10+ minute se offline ho
#    2. Auto-reply toggle ON ho
#    3. Msg #1 ya phir har 3rd msg par
# ============================================================

import asyncio
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
)
from telethon.tl.types import (
    User,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

import config
import database as db

logger = logging.getLogger(__name__)

SESSIONS_DIR  = "sessions"
REPLY_EVERY_N = 3
OFFLINE_MINS  = 10          # ← yahan change karo agar limit badlni ho

os.makedirs(SESSIONS_DIR, exist_ok=True)


# ── Per-user state ────────────────────────────────────────

@dataclass
class UserSession:
    client: TelegramClient
    msg_counter: dict = field(default_factory=lambda: defaultdict(int))
    phone: str = ""
    phone_code_hash: str = ""


_sessions: dict[int, UserSession] = {}


def _session_path(user_id: int) -> str:
    return os.path.join(SESSIONS_DIR, f"user_{user_id}")


def _make_client(user_id: int) -> TelegramClient:
    return TelegramClient(
        _session_path(user_id),
        config.API_ID,
        config.API_HASH,
    )


# ── Offline check ─────────────────────────────────────────

async def _is_user_offline_long_enough(client: TelegramClient) -> bool:
    """
    Apna khud ka status check karta hai.
    True return karta hai agar:
      - Status 'offline' hai  AND
      - Last seen >= OFFLINE_MINS minute pehle ho
    """
    try:
        me = await client.get_me()
        # get_me() mein status nahi hoti, full user fetch karna padta hai
        full_me = await client.get_entity(me.id)
        status  = full_me.status
    except Exception as e:
        logger.warning(f"Could not fetch own status: {e}")
        # Status fetch na ho sake to safe side par reply karo
        return True

    if isinstance(status, UserStatusOnline):
        # Abhi online hai — reply mat karo
        return False

    if isinstance(status, UserStatusRecently):
        # "Recently" matlab 30 min ke andar online tha
        # Hum consider karte hain ye offline_mins se kam hai
        return False

    if isinstance(status, UserStatusOffline):
        was_online = status.was_online  # datetime (UTC)
        now        = datetime.now(timezone.utc)
        diff_mins  = (now - was_online).total_seconds() / 60
        logger.debug(f"User offline since {diff_mins:.1f} min ago")
        return diff_mins >= OFFLINE_MINS

    # UserStatusEmpty / UserStatusLongTimeAgo → offline maan lo
    return True


# ── Auth helpers ──────────────────────────────────────────

async def send_code(user_id: int, phone: str) -> str:
    await _disconnect_user(user_id)
    client = _make_client(user_id)
    await client.connect()
    result = await client.send_code_request(phone)
    _sessions[user_id] = UserSession(
        client=client,
        phone=phone,
        phone_code_hash=result.phone_code_hash,
    )
    return result.phone_code_hash


async def sign_in_with_code(user_id: int, code: str) -> str:
    sess = _sessions.get(user_id)
    if not sess:
        raise RuntimeError("No active login session. Use /login first.")
    code = code.replace(" ", "")
    try:
        await sess.client.sign_in(
            sess.phone, code, phone_code_hash=sess.phone_code_hash
        )
        await _attach_handler(user_id, sess)
        return "ok"
    except SessionPasswordNeededError:
        return "2fa_needed"
    except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
        raise e


async def sign_in_with_2fa(user_id: int, password: str) -> bool:
    sess = _sessions.get(user_id)
    if not sess:
        raise RuntimeError("No active login session.")
    await sess.client.sign_in(password=password)
    await _attach_handler(user_id, sess)
    return True


async def logout(user_id: int) -> bool:
    sess = _sessions.get(user_id)
    if sess and sess.client.is_connected():
        try:
            await sess.client.log_out()
        except Exception:
            pass
    await _disconnect_user(user_id)
    path = _session_path(user_id) + ".session"
    if os.path.exists(path):
        os.remove(path)
    return True


async def _disconnect_user(user_id: int):
    sess = _sessions.pop(user_id, None)
    if sess and sess.client.is_connected():
        await sess.client.disconnect()


def is_connected(user_id: int) -> bool:
    s = _sessions.get(user_id)
    return bool(s and s.client.is_connected())


# ── Resume all sessions on restart ───────────────────────

async def resume_all_sessions() -> int:
    resumed = 0
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".session"):
            continue
        try:
            uid = int(fname.replace("user_", "").replace(".session", ""))
        except ValueError:
            continue
        if not await db.is_logged_in(uid):
            continue
        try:
            client = _make_client(uid)
            await client.connect()
            if await client.is_user_authorized():
                sess = UserSession(client=client)
                _sessions[uid] = sess
                await _attach_handler(uid, sess)
                logger.info(f"Resumed session for user {uid}.")
                resumed += 1
            else:
                await client.disconnect()
                await db.set_logged_in(uid, False)
        except Exception as e:
            logger.warning(f"Could not resume session for user {uid}: {e}")
    return resumed


# ── Auto-reply handler ────────────────────────────────────

async def _attach_handler(user_id: int, sess: UserSession):

    @sess.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def _auto_reply(event):
        sender = await event.get_sender()

        # Bots aur system ko ignore karo
        if not isinstance(sender, User) or sender.bot or sender.id == 777000:
            return

        # Toggle check
        if not await db.is_enabled(user_id):
            return

        # ── Offline duration check ─────────────────────
        offline_enough = await _is_user_offline_long_enough(sess.client)
        if not offline_enough:
            logger.debug(
                f"[user {user_id}] Skipping reply — user online or offline < {OFFLINE_MINS} min"
            )
            return

        # ── Message counter (1st msg + every Nth) ─────
        chat_id = event.chat_id
        sess.msg_counter[chat_id] += 1
        count = sess.msg_counter[chat_id]

        should_reply = (count == 1) or ((count - 1) % REPLY_EVERY_N == 0)
        if not should_reply:
            return

        message = await db.get_message(user_id)
        if message:
            await asyncio.sleep(0.8)
            await event.reply(message)
            logger.info(
                f"[user {user_id}] Auto-replied to {sender.id} "
                f"({sender.first_name}) [msg #{count}, offline ✅]"
            )

    logger.info(
        f"Handler attached for user {user_id}. "
        f"Offline threshold: {OFFLINE_MINS} min."
    )
