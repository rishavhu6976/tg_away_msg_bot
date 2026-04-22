# ============================================================
#  main.py  —  Entry point
# ============================================================

import asyncio
import logging

import config
import database as db
import userbot
from controlbot import build_app

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _check_config():
    errors = []
    if not config.API_ID:   errors.append("API_ID is not set in config.py")
    if not config.API_HASH: errors.append("API_HASH is not set in config.py")
    if not config.BOT_TOKEN:errors.append("BOT_TOKEN is not set in config.py")
    if not config.OWNER_ID: errors.append("OWNER_ID is not set in config.py")
    if errors:
        for e in errors:
            logger.error(f"  ✗ {e}")
        raise SystemExit("\n❌ Fill in config.py before running.\n")


async def main():
    _check_config()

    await db.init_db()
    logger.info("✅ Database ready.")

    # Resume every saved session — each user gets their own client
    resumed = await userbot.resume_all_sessions()
    logger.info(f"✅ Resumed {resumed} user session(s).")

    app = build_app()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message", "callback_query"])

    print("\n" + "═" * 50)
    print("  Telegram Auto-Reply Userbot is running!")
    print(f"  Resumed sessions : {resumed}")
    print(f"  Owner ID         : {config.OWNER_ID}")
    print("  Press Ctrl+C to stop.")
    print("═" * 50 + "\n")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down…")
        # Disconnect all user clients cleanly
        for uid in list(userbot._sessions.keys()):
            try:
                sess = userbot._sessions[uid]
                if sess.client.is_connected():
                    await sess.client.disconnect()
            except Exception:
                pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Goodbye! 👋")


if __name__ == "__main__":
    asyncio.run(main())
