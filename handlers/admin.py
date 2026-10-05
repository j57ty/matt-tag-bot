import html
import logging
from typing import Optional, Tuple
from telegram import Update, User
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

import config
import database

logger = logging.getLogger(__name__)


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks whether the user executing the command has admin privileges."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return False

    # Check if user is in superadmin list
    if user.id in config.SUPERADMIN_IDS:
        return True

    # If it's a private chat and not in superadmin list, deny
    if chat.type == ChatType.PRIVATE:
        return False

    # Check Telegram group administrator status
    try:
        chat_member = await context.bot.get_chat_member(chat.id, user.id)
        if chat_member.status in ("creator", "administrator"):
            return True
    except Exception as e:
        logger.error(f"Error checking admin status for user {user.id} in chat {chat.id}: {e}")

    return False


async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Validates admin permissions and informs unauthorized users."""
    if await is_admin(update, context):
        return True

    if update.message:
        await update.message.reply_text(
            "⛔ <b>Access Denied:</b> This bot is configured for administrators only.",
            parse_mode=ParseMode.HTML
        )
    return False


async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically records/updates users seen in the group to enable linking by username."""
    user = update.effective_user
    if user and not user.is_bot:
        database.cache_user(
            user_id=user.id,
            tg_username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command."""
    if not await admin_guard(update, context):
        return

    welcome_text = (
        "👋 <b>Welcome to the X Member Tagging Bot!</b>\n\n"
        "This bot maps Telegram group members to their X (Twitter) handles and allows admins "
        "to instantly tag members using their X handle.\n\n"
        "<b>Available Admin Commands:</b>\n"
        "• <code>/tag &lt;x_handle&gt; [message]</code> — Tag/mention a member by their X handle\n"
        "• <code>/link &lt;x_handle&gt;</code> — Reply to any user's message to link them to an X handle\n"
        "• <code>/link @tg_username &lt;x_handle&gt;</code> — Link a user by their Telegram username\n"
        "• <code>/unlink &lt;x_handle | @tg_username&gt;</code> — Remove an existing link\n"
        "• <code>/lookup &lt;x_handle | @tg_username&gt;</code> — View member details\n"
        "• <code>/list</code> — List all registered member mappings\n"
        "• <code>/help</code> — View full command guide and examples"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help command."""
    if not await admin_guard(update, context):
        return

    help_text = (
        "📖 <b>Admin Command Reference:</b>\n\n"
        "<b>1. Tagging a Member:</b>\n"
        "• <code>/tag &lt;x_handle&gt; [optional message]</code>\n"
        "<i>You can also use:</i> <code>#tag &lt;x_handle&gt;</code> or <code>!tag &lt;x_handle&gt;</code>\n"
        "<i>Example:</i> <code>/tag elonmusk Please review the latest announcement!</code>\n\n"
        "<b>2. Linking an X Handle to a Telegram User:</b>\n"
        "• <b>Option A (Easiest):</b> Reply to any message sent by the member in the group with:\n"
        "  <code>/link &lt;x_handle&gt;</code>\n"
        "  <i>Example reply:</i> <code>/link elonmusk</code>\n\n"
        "• <b>Option B:</b> Link by their Telegram username:\n"
        "  <code>/link @telegram_username &lt;x_handle&gt;</code>\n"
        "  <i>Example:</i> <code>/link @alice crypto_queen</code>\n\n"
        "• <b>Option C:</b> Link by their numeric Telegram User ID:\n"
        "  <code>/link &lt;user_id&gt; &lt;x_handle&gt;</code>\n\n"
        "<b>3. Managing Links:</b>\n"
        "• <code>/unlink &lt;x_handle | @tg_username | user_id&gt;</code>\n"
        "• <code>/lookup &lt;x_handle | @tg_username | user_id&gt;</code>\n"
        "• <code>/list</code>"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Links a Telegram user to an X handle.
    Syntax:
      - By reply: /link <x_handle>
      - By mention/ID: /link <@tg_user | user_id> <x_handle>
    """
    if not await admin_guard(update, context):
        return

    message = update.message
    args = context.args or []

    target_user_id: Optional[int] = None
    target_username: Optional[str] = None
    target_first_name: Optional[str] = None
    target_last_name: Optional[str] = None
    x_handle: Optional[str] = None

    # Case 1: Admin replied to a user's message
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user: User = message.reply_to_message.from_user
        if replied_user.is_bot:
            await message.reply_text("❌ You cannot link a bot account.", parse_mode=ParseMode.HTML)
            return

        if not args:
            await message.reply_text(
                "⚠️ <b>Usage when replying:</b> <code>/link &lt;x_handle&gt;</code>\n"
                "<i>Example:</i> <code>/link elonmusk</code>",
                parse_mode=ParseMode.HTML
            )
            return

        target_user_id = replied_user.id
        target_username = replied_user.username
        target_first_name = replied_user.first_name
        target_last_name = replied_user.last_name

        # If admin replied and typed "/link @username <tag>", use the second argument as the tag
        if len(args) >= 2 and args[0].lstrip("@").lower() == (replied_user.username or "").lower():
            x_handle = args[1]
        else:
            x_handle = args[-1] if len(args) == 1 else args[0]

        # Auto-cache this user immediately
        database.cache_user(target_user_id, target_username, target_first_name, target_last_name)

    # Case 2: Provided 2 arguments without replying: /link <@tg_user | user_id> <x_handle>
    elif len(args) >= 2:
        user_param = args[0]
        x_handle = args[1]

        if user_param.isdigit():
            target_user_id = int(user_param)
            cached = database.find_cached_user_by_id(target_user_id)
            if cached:
                target_username = cached.get("tg_username")
                target_first_name = cached.get("first_name")
                target_last_name = cached.get("last_name")
        else:
            clean_param = database.normalize_handle(user_param)
            cached = database.find_cached_user_by_username(clean_param)

            # If not in local cache, check if they are in the group's administrators list
            if not cached and message.chat:
                try:
                    chat_admins = await context.bot.get_chat_administrators(message.chat.id)
                    for adm in chat_admins:
                        if adm.user and (adm.user.username or "").lower() == clean_param:
                            database.cache_user(
                                adm.user.id, adm.user.username, adm.user.first_name, adm.user.last_name
                            )
                            cached = {
                                "user_id": adm.user.id,
                                "tg_username": adm.user.username,
                                "first_name": adm.user.first_name,
                                "last_name": adm.user.last_name
                            }
                            break
                except Exception as e:
                    logger.debug("Could not inspect chat administrators: %s", e)

            if cached:
                target_user_id = cached["user_id"]
                target_username = cached.get("tg_username")
                target_first_name = cached.get("first_name")
                target_last_name = cached.get("last_name")
            else:
                await message.reply_text(
                    f"⚠️ <b>User @{html.escape(clean_param)} has not been seen by the bot yet.</b>\n\n"
                    "Telegram doesn't allow bots to search for arbitrary usernames that haven't sent a message.\n\n"
                    "<b>Two quick ways to link them:</b>\n"
                    "1. <b>Reply directly</b> to any message that user sent in this group with:\n"
                    f"   <code>/link {html.escape(x_handle)}</code>\n"
                    "2. Or ask them to send a message in this group first, then retry this command.",
                    parse_mode=ParseMode.HTML
                )
                return
    else:
        await message.reply_text(
            "⚠️ <b>How to link a user:</b>\n\n"
            "<b>Option 1 (Recommended):</b> Reply to their message with:\n"
            "<code>/link &lt;x_handle&gt;</code>\n\n"
            "<b>Option 2:</b> Specify their Telegram username:\n"
            "<code>/link @telegram_username &lt;x_handle&gt;</code>\n\n"
            "<b>Option 3:</b> Specify their Telegram User ID:\n"
            "<code>/link &lt;user_id&gt; &lt;x_handle&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return

    clean_x = database.normalize_handle(x_handle)
    if not clean_x:
        await message.reply_text("❌ Invalid X handle provided.", parse_mode=ParseMode.HTML)
        return

    # Save to database
    record = database.upsert_member(
        user_id=target_user_id,
        x_handle=clean_x,
        tg_username=target_username,
        first_name=target_first_name,
        last_name=target_last_name
    )

    display_name = record.get("first_name") or "Member"
    tg_user_text = f"@{record['tg_username']}" if record.get("tg_username") else f"ID: {target_user_id}"

    # Attempt to assign the Group Custom Title badge (shows next to their name on messages)
    badge_note = ""
    if message.chat and message.chat.type in (ChatType.SUPERGROUP, ChatType.GROUP):
        success_badge, badge_val = await try_set_custom_title(
            context, message.chat.id, target_user_id, clean_x
        )
        if success_badge:
            badge_note = f"\n🏷️ <b>Name Badge:</b> Set to <code>{html.escape(badge_val)}</code> (now appears next to their name on group messages!)"
        else:
            badge_note = (
                "\nℹ️ <b>Name Badge:</b> Could not set title badge automatically.\n"
                "<i>(Tip: Ensure this group is a Supergroup and grant the bot the 'Add new admins' permission).</i>"
            )

    response_text = (
        "✅ <b>Member Successfully Linked!</b>\n\n"
        f"• <b>Tag:</b> <code>{html.escape(clean_x)}</code>\n"
        f"• <b>Telegram Account:</b> <a href=\"tg://user?id={target_user_id}\">{html.escape(display_name)}</a> ({html.escape(tg_user_text)})\n"
        f"• <b>Telegram ID:</b> <code>{target_user_id}</code>{badge_note}\n\n"
        f"<i>You can now mention/find them anytime using:</i> <code>/tag {html.escape(clean_x)}</code>"
    )
    await message.reply_text(response_text, parse_mode=ParseMode.HTML)


async def try_set_custom_title(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, tag: str
) -> Tuple[bool, str]:
    """
    Attempts to assign a custom administrator title badge (appears next to their name in the group).
    Telegram allows up to 16 characters for custom titles.
    """
    badge = tag[:16]
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        # If user is not yet an admin, promote them with minimal rights to hold the title
        if member.status not in ("creator", "administrator"):
            await context.bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_manage_chat=True
            )

        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=badge
        )
        return True, badge
    except Exception as e:
        logger.warning("Could not set custom title badge for user %s: %s", user_id, e)
        return False, str(e)


async def try_remove_custom_title(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
):
    """Attempts to remove custom administrator title badge."""
    try:
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=""
        )
    except Exception as e:
        logger.warning("Could not remove custom title for user %s: %s", user_id, e)


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a linked member by X handle, @username, or Telegram User ID."""
    if not await admin_guard(update, context):
        return

    message = update.message
    args = context.args or []

    target_user_id: Optional[int] = None
    if not args and message.reply_to_message and message.reply_to_message.from_user:
        target_user_id = message.reply_to_message.from_user.id
        identifier = str(target_user_id)
    elif args:
        identifier = args[0]
        if identifier.isdigit():
            target_user_id = int(identifier)
        else:
            clean = database.normalize_handle(identifier)
            m = database.get_member_by_x_handle(clean) or database.get_member_by_tg_username(clean)
            if m:
                target_user_id = m.get("user_id")
    else:
        await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/unlink &lt;x_handle | @tg_username | user_id&gt;</code>\n"
            "Or reply to a member's message with <code>/unlink</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    # Clear custom title if in a group
    if target_user_id and message.chat and message.chat.type in (ChatType.SUPERGROUP, ChatType.GROUP):
        await try_remove_custom_title(context, message.chat.id, target_user_id)

    success = database.remove_member(identifier)
    clean_id = database.normalize_handle(identifier)
    if success:
        await message.reply_text(
            f"✅ Link and badge for <code>{html.escape(clean_id)}</code> have been removed.",
            parse_mode=ParseMode.HTML

        )
    else:
        await message.reply_text(
            f"❌ No registered member found matching <code>{html.escape(clean_id)}</code>.",
            parse_mode=ParseMode.HTML
        )


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Looks up a user by their X handle and tags their Telegram account.
    Syntax: /tag <x_handle> [optional message]
    """
    if not await admin_guard(update, context):
        return

    message = update.message
    args = context.args or []

    if not args:
        await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/tag &lt;x_handle&gt; [optional message]</code>\n"
            "<i>Example:</i> <code>/tag elonmusk Please check the task updates!</code>",
            parse_mode=ParseMode.HTML
        )
        return

    x_handle = args[0]
    custom_message = " ".join(args[1:]).strip() if len(args) > 1 else ""

    await execute_tag(update, x_handle, custom_message)


async def execute_tag(update: Update, x_handle: str, custom_message: str = ""):
    """Helper to perform the tag lookup and generate the notification mention."""
    clean_x = database.normalize_handle(x_handle)
    member = database.get_member_by_x_handle(clean_x)

    if not member:
        await update.message.reply_text(
            f"❌ <b>No member found</b> registered with tag <code>{html.escape(clean_x)}</code>.\n"
            f"Link them first using <code>/link &lt;user&gt; {html.escape(clean_x)}</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    user_id = member["user_id"]
    tg_username = member.get("tg_username")
    first_name = member.get("first_name") or "Member"

    # Direct Telegram mention link that guarantees notification
    mention_link = f"<a href=\"tg://user?id={user_id}\">{html.escape(first_name)}</a>"
    username_display = f"(@{html.escape(tg_username)})" if tg_username else ""

    lines = [
        f"🎯 <b>Tag:</b> <code>{html.escape(clean_x)}</code>",
        f"👤 <b>Member:</b> {mention_link} {username_display}"
    ]

    if custom_message:
        lines.append(f"\n💬 <b>Message:</b> {html.escape(custom_message)}")

    response_text = "\n".join(lines)
    await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)


async def handle_text_shortcuts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Supports shortcut triggers like `#tag <x_handle> [msg]` or `!tag <x_handle> [msg]`
    without needing the leading slash.
    """
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    if text.startswith(("#tag ", "!tag ")):
        if not await admin_guard(update, context):
            return
        parts = text.split()
        if len(parts) >= 2:
            x_handle = parts[1]
            custom_message = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
            await execute_tag(update, x_handle, custom_message)


async def lookup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Looks up registration information for a member."""
    if not await admin_guard(update, context):
        return

    message = update.message
    args = context.args or []

    if not args and message.reply_to_message and message.reply_to_message.from_user:
        identifier = str(message.reply_to_message.from_user.id)
    elif args:
        identifier = args[0]
    else:
        await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/lookup &lt;x_handle | @tg_username | user_id&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return

    clean_id = database.normalize_handle(identifier)
    member = None
    if clean_id.isdigit():
        member = database.get_member_by_user_id(int(clean_id))
    else:
        member = database.get_member_by_x_handle(clean_id) or database.get_member_by_tg_username(clean_id)

    if not member:
        await message.reply_text(
            f"❌ No record found for <code>{html.escape(clean_id)}</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    display_name = member.get("first_name") or "Member"
    tg_username = f"@{member['tg_username']}" if member.get("tg_username") else "None"
    created_at = member.get("created_at", "N/A")[:19].replace("T", " ")

    info_text = (
        "📋 <b>Member Record:</b>\n\n"
        f"• <b>Tag:</b> <code>{html.escape(member['x_handle'])}</code>\n"
        f"• <b>Telegram Name:</b> <a href=\"tg://user?id={member['user_id']}\">{html.escape(display_name)}</a>\n"
        f"• <b>Telegram Username:</b> {html.escape(tg_username)}\n"
        f"• <b>Telegram User ID:</b> <code>{member['user_id']}</code>\n"
        f"• <b>Registered On:</b> <code>{created_at} UTC</code>"
    )
    await message.reply_text(info_text, parse_mode=ParseMode.HTML)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all registered member mappings."""
    if not await admin_guard(update, context):
        return

    members = database.list_all_members()
    if not members:
        await update.message.reply_text(
            "📂 <b>Database is empty.</b> No members have been linked yet.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"📋 <b>Registered Members ({len(members)} total):</b>\n"]
    for i, m in enumerate(members, start=1):
        name = m.get("first_name") or "Member"
        tg_user = f"(@{m['tg_username']})" if m.get("tg_username") else f"(ID: {m['user_id']})"
        lines.append(
            f"{i}. <code>{html.escape(m['x_handle'])}</code> ➔ <a href=\"tg://user?id={m['user_id']}\">{html.escape(name)}</a> {html.escape(tg_user)}"
        )

    # Telegram message length limit is 4096 characters, chunk if necessary
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 3800:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += line + "\n"

    if chunk:
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Utility command returning the user's Telegram ID and username."""
    user = update.effective_user
    if not user:
        return

    text = (
        "🆔 <b>Your Telegram Information:</b>\n"
        f"• <b>User ID:</b> <code>{user.id}</code>\n"
        f"• <b>Username:</b> @{html.escape(user.username) if user.username else 'None'}\n"
        f"• <b>First Name:</b> {html.escape(user.first_name or '')}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
