# Telegram Member Tagging Bot (X / Twitter Handle Tracking)

A Telegram management bot built with `python-telegram-bot` and SQLite that lets group admins link Telegram members to their X (Twitter) handles and tag them directly in the chat using their X handle.

---

## ✨ Features

- **Admin-Only Security:** Only chat administrators (and designated superadmins) can issue commands or link members.
- **Instant Mention / Tagging:** Use `/tag <x_handle> [message]` (or `#tag <x_handle>`) to look up a member's X handle and ping their Telegram account.
- **Guaranteed Push Notifications:** Uses direct Telegram user mention links (`tg://user?id=...`) to ensure members receive notification pings even if they don't have a public `@username` or recently changed it.
- **Multiple Linking Methods:**
  - **By Reply (Easiest):** Reply to any message sent by a member with `/link <x_handle>`.
  - **By Username:** `/link @username <x_handle>`.
  - **By User ID:** `/link <user_id> <x_handle>`.
- **Auto-Caching:** Automatically tracks members who talk in the group so they can be looked up and linked by `@username` without manual ID fetching.
- **SQLite Storage:** Lightweight, zero-configuration local database.

---

## 🚀 Setup Guide

### 1. Create your Bot on Telegram
1. Open Telegram and search for [`@BotFather`](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts to choose a name and username for your bot.
3. BotFather will provide an API token (e.g. `7123456789:AAH...`). Copy this token.
4. *(Recommended)* Disable group privacy so the bot can read messages and track member activity:
   - In `@BotFather`, send `/setprivacy`.
   - Select your bot.
   - Choose **Disable**.

### 2. Configure Environment
1. In the project folder, copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and paste your bot token:
   ```env
   BOT_TOKEN=your_token_from_botfather_here
   SUPERADMIN_IDS=123456789
   ```

### 3. Add Bot to your Telegram Group
1. Add the bot to your Telegram group.
2. Promote the bot to an **Administrator** in the group.
3. Make sure you (and any other teammates who will use the commands) are also administrators in the group.

### 4. Run the Bot
Using the pre-configured virtual environment:
```powershell
.\.venv\Scripts\python.exe bot.py
```

---

## 🛠 Admin Commands Reference

| Command | Description | Example |
| :--- | :--- | :--- |
| `/tag <x_handle> [msg]` | Find and tag/mention the Telegram user registered to the X handle | `/tag elonmusk Please check the pinned post!` |
| `#tag <x_handle> [msg]` | Shortcut syntax for tagging without slash | `#tag elonmusk check this` |
| `/link <x_handle>` | **(In reply to a member)** Links the member to that X handle | Reply to member: `/link elonmusk` |
| `/link @user <x_handle>` | Links a user by Telegram username | `/link @john_doe elonmusk` |
| `/link <id> <x_handle>` | Links a user by Telegram numeric ID | `/link 987654321 elonmusk` |
| `/unlink <x_handle>` | Removes a member's link from the database | `/unlink elonmusk` |
| `/lookup <x_handle>` | Views details of a linked member | `/lookup elonmusk` |
| `/list` | Lists all linked members in the database | `/list` |
| `/myinfo` | Displays your own Telegram user ID | `/myinfo` |
| `/help` | Displays the help manual in Telegram | `/help` |

---

## 📂 Project Structure

```
telegram-tag-bot/
│
├── bot.py             # Main entry point, sets up handlers and starts polling
├── config.py          # Environment configuration loader (.env)
├── database.py        # SQLite schema and query methods
├── handlers/
│   ├── __init__.py
│   └── admin.py       # Admin verification and command handlers
├── requirements.txt   # Python dependencies
├── .env.example       # Template for environment variables
└── README.md          # Setup and command guide
```
