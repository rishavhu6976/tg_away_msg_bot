# 🤖 Telegram Auto-Reply Userbot

A Telegram userbot that auto-replies when someone messages you — with a full control bot and admin panel.

---

## 📁 Project Structure

```
tg-autoreply-bot/
├── main.py          # Entry point
├── config.py        # API keys & settings
├── database.py      # SQLite storage
├── userbot.py       # Telethon userbot (auto-reply engine)
├── controlbot.py    # User control panel bot
├── admin.py         # Admin commands module
└── requirements.txt
```

---

## ⚙️ Setup

### 1. Get credentials

- **API ID & Hash** → https://my.telegram.org/apps
- **Bot Token** → @BotFather on Telegram

### 2. Fill in `config.py`

```python
API_ID    = 12345678
API_HASH  = "your_hash_here"
BOT_TOKEN = "your_bot_token"
OWNER_ID  = 987654321          # Your Telegram user ID
ADMIN_IDS = [111222333]        # Extra admins (optional)
```

Get your user ID from @userinfobot on Telegram.

### 3. Install & run

```bash
pip install -r requirements.txt
python main.py
```

---

## 🎮 User Commands

| Command    | Description                        |
|------------|------------------------------------|
| `/start`   | Dashboard with all controls        |
| `/login`   | Log in to your Telegram account    |
| `/logout`  | Log out and stop userbot           |
| `/toggle`  | Turn auto-reply ON or OFF          |
| `/setmsg`  | Change your auto-reply message     |
| `/preview` | Preview your current message       |
| `/status`  | Check current status               |
| `/cancel`  | Cancel any pending operation       |

---

## 🛡️ Admin Commands

| Command        | Description                              |
|----------------|------------------------------------------|
| `/admin`       | Open the full admin panel (buttons UI)   |
| `/users`       | List all registered users                |
| `/stats`       | Bot-wide statistics                      |
| `/broadcast`   | Send a message to all bot users          |

### Admin Panel buttons

| Button            | What it does                                        |
|-------------------|-----------------------------------------------------|
| 👥 All Users      | Full list: name, ID, login status, auto-reply state |
| 🔑 Logged-In      | Only users currently logged in + their phone        |
| 📋 User Messages  | Each user's configured auto-reply message           |
| 📡 Broadcast      | Send a message to everyone using the bot            |
| 📜 Broadcast Log  | History of past broadcasts with delivery counts     |
| 🚫 Force Logout   | Log out any user by their ID                        |

---

## 🔒 Security Notes

- Sessions are stored locally in `userbot.session`
- Only `OWNER_ID` and `ADMIN_IDS` can access admin commands
- The userbot only reads **incoming private messages** to trigger auto-reply — it does not store or expose anyone's private conversations
- The "User Messages" admin view shows each user's **configured auto-reply text**, not their actual Telegram chat history
- Never share your `.session` file or `autoreply.db` with anyone
