# ============================================================
#  config.py  —  Fill in your credentials before running
# ============================================================

# ── Step 1: Get these from https://my.telegram.org/apps ──
API_ID   = 0           # e.g. 12345678
API_HASH = ""          # e.g. "abcdef1234567890abcdef1234567890"

# ── Step 2: Create a bot via @BotFather and paste token ──
BOT_TOKEN = ""         # e.g. "7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ── Step 3: Your Telegram user ID (get from @userinfobot) ─
OWNER_ID  = 0          # e.g. 987654321

# ── Step 4: Additional admin IDs (can use admin commands) ─
# The OWNER_ID is always an admin. Add more admins here:
ADMIN_IDS: list = []   # e.g. [111222333, 444555666]

# ── Session file name (no need to change) ─────────────────
SESSION_NAME = "userbot"

# ── Default auto-reply message ────────────────────────────
DEFAULT_MESSAGE = (
    "👋 Hi! I'm currently unavailable.\n"
    "I'll get back to you as soon as I'm online. 🙏"
)
