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
        "• <code>/synctags</code> — Auto-sync all manually assigned admin titles into the bot\n"
        "• <code>/unlink &lt;tag | @tg_username | user_id&gt;</code> — Remove an existing tag\n"
        "• <code>/lookup &lt;tag | @tg_username | user_id&gt;</code> — View member details\n"
        "• <code>/list</code> — List all registered members and tags\n"
        "• <code>/demote [@user]</code> — Demote a user back to normal member"
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
        x_handle=clean_x,
        tg_username=target_username,
        user_id=target_user_id,
        first_name=target_first_name,
        last_name=target_last_name
    )

    display_name = record.get("first_name") or (f"@{record['tg_username']}" if record.get("tg_username") else "Member")
    tg_user_text = f"@{record['tg_username']}" if record.get("tg_username") else f"ID: {target_user_id}"

    user_link = f"<a href=\"tg://user?id={target_user_id}\">{html.escape(display_name)}</a>" if target_user_id else html.escape(display_name)
    response_text = (
        "✅ <b>Member Successfully Linked!</b>\n\n"
        f"• <b>Tag:</b> <code>{html.escape(clean_x)}</code>\n"
        f"• <b>Telegram Account:</b> {user_link} ({html.escape(tg_user_text)})\n"
        f"• <b>Telegram ID:</b> <code>{target_user_id or 'Auto-caches when user speaks'}</code>\n\n"
        f"<i>You can now mention/find them anytime using:</i> <code>/tag {html.escape(clean_x)}</code>"
    )
    await message.reply_text(response_text, parse_mode=ParseMode.HTML)


async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demotes a user back to a regular member in the group."""
    if not await admin_guard(update, context):
        return

    message = update.message
    args = context.args or []
    target_user_id = None
    target_name = "User"

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
    elif args:
        param = args[0]
        if param.isdigit():
            target_user_id = int(param)
        else:
            clean = database.normalize_handle(param)
            cached = database.find_cached_user_by_username(clean)
            if cached:
                target_user_id = cached["user_id"]
                target_name = cached.get("first_name") or "User"
            else:
                try:
                    chat_admins = await context.bot.get_chat_administrators(message.chat.id)
                    for adm in chat_admins:
                        if adm.user and (adm.user.username or "").lower() == clean:
                            target_user_id = adm.user.id
                            target_name = adm.user.first_name
                            break
                except Exception:
                    pass

    if not target_user_id:
        await message.reply_text(
            "⚠️ <b>Usage:</b> Reply to the member with <code>/demote</code>, or type <code>/demote @username</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        await context.bot.promote_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id,
            can_manage_chat=False,
            can_change_info=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False
        )
        await message.reply_text(
            f"✅ <b>{html.escape(target_name)}</b> has been demoted back to a regular member.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.reply_text(
            f"❌ Could not demote user: {html.escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a linked member by X handle, @username, or Telegram User ID."""
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
            "⚠️ <b>Usage:</b> <code>/unlink &lt;x_handle | @tg_username | user_id&gt;</code>\n"
            "Or reply to a member's message with <code>/unlink</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    success = database.remove_member(identifier)
    clean_id = database.normalize_handle(identifier)
    if success:
        await message.reply_text(
            f"✅ Link for <code>{html.escape(clean_id)}</code> has been removed.",
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

    await execute_tag(update, context, x_handle, custom_message)


async def execute_tag(update: Update, context: ContextTypes.DEFAULT_TYPE, x_handle: str, custom_message: str = ""):
    """Helper to perform the tag lookup and generate the notification mention."""
    clean_x = database.normalize_handle(x_handle)
    member = database.get_member_by_x_handle(clean_x)

    # If not found in database, check if any group administrator has this tag as their custom_title
    if not member and update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
        try:
            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            for adm in admins:
                adm_title = (getattr(adm, "custom_title", None) or "").strip()
                if adm_title and database.normalize_handle(adm_title) == clean_x:
                    u = adm.user
                    database.upsert_member(
                        user_id=u.id,
                        x_handle=clean_x,
                        tg_username=u.username,
                        first_name=u.first_name,
                        last_name=u.last_name
                    )
                    member = database.get_member_by_x_handle(clean_x)
                    break
        except Exception as e:
            logger.debug("Error checking administrators for custom_title: %s", e)

    if not member:
        await update.message.reply_text(
            f"❌ <b>No member found</b> registered with tag <code>{html.escape(clean_x)}</code>.\n"
            f"Link them using <code>/link &lt;user&gt; {html.escape(clean_x)}</code> or run <code>/synctags</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    user_id = member.get("user_id")
    tg_username = member.get("tg_username")
    first_name = member.get("first_name") or "Member"

    if user_id:
        mention_link = f"<a href=\"tg://user?id={user_id}\">{html.escape(first_name)}</a>"
        username_display = f"(@{html.escape(tg_username)})" if tg_username else ""
    elif tg_username:
        mention_link = f"@{html.escape(tg_username)}"
        username_display = ""
    else:
        mention_link = "Member"
        username_display = ""

    lines = [
        f"🎯 <b>Tag:</b> <code>{html.escape(clean_x)}</code>",
        f"👤 <b>Member:</b> {mention_link} {username_display}".strip()
    ]

    if custom_message:
        lines.append(f"\n💬 <b>Message:</b> {html.escape(custom_message)}")

    response_text = "\n".join(lines)
    await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)


async def synctags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Scans all group administrators and automatically imports their Custom Titles as tags.
    """
    if not await admin_guard(update, context):
        return

    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ <code>/synctags</code> must be run inside your Telegram group.",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to inspect group administrators: {html.escape(str(e))}",
            parse_mode=ParseMode.HTML
        )
        return

    synced = []
    for adm in admins:
        if adm.user.is_bot:
            continue
        title = (getattr(adm, "custom_title", None) or "").strip()
        if title:
            clean_tag = database.normalize_handle(title)
            database.upsert_member(
                user_id=adm.user.id,
                x_handle=clean_tag,
                tg_username=adm.user.username,
                first_name=adm.user.first_name,
                last_name=adm.user.last_name
            )
            name = adm.user.first_name or "Member"
            tg_user = f"(@{adm.user.username})" if adm.user.username else f"(ID: {adm.user.id})"
            synced.append(
                f"• <code>{html.escape(clean_tag)}</code> ➔ <a href=\"tg://user?id={adm.user.id}\">{html.escape(name)}</a> {html.escape(tg_user)}"
            )

    if not synced:
        await update.message.reply_text(
            "ℹ️ <b>No Custom Titles found.</b>\n\n"
            "None of the administrators in this group currently have a Custom Title badge set in "
            "<b>Group Settings ➔ Administrators</b>.",
            parse_mode=ParseMode.HTML
        )
        return

    response = (
        f"✅ <b>Successfully synced {len(synced)} tag(s) from group titles:</b>\n\n"
        + "\n".join(synced)
        + "\n\n<i>You can now mention any of them using <code>/tag &lt;tag&gt;</code>!</i>"
    )
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)


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
            await execute_tag(update, context, x_handle, custom_message)


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
        uid = m.get("user_id")
        name = m.get("first_name")
        tg_user = m.get("tg_username")
        if uid and name:
            display = f"<a href=\"tg://user?id={uid}\">{html.escape(name)}</a>" + (f" (@{html.escape(tg_user)})" if tg_user else "")
        elif tg_user:
            display = f"@{html.escape(tg_user)}"
        elif uid:
            display = f"ID: <code>{uid}</code>"
        else:
            display = "Member"
        lines.append(
            f"{i}. <code>{html.escape(m['x_handle'])}</code> ➔ {display}"
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


async def bulklink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Links multiple members in bulk from pasted text.
    Usage:
    /bulklink
    @username tag
    @username2 tag2
    """
    if not await admin_guard(update, context):
        return

    message = update.message
    text = message.text or ""
    lines = text.split("\n")[1:]
    if not lines and context.args:
        lines = [" ".join(context.args)]

    count = 0
    for line in lines:
        parts = line.strip().split()
        at_parts = [p.lstrip("@").strip() for p in parts if "@" in p]
        if len(at_parts) >= 2:
            clean_tg = database.normalize_handle(at_parts[0])
            clean_tag = database.normalize_handle(at_parts[1])
            database.upsert_member(x_handle=clean_tag, tg_username=clean_tg)
            count += 1
        elif len(parts) >= 2:
            clean_tg = database.normalize_handle(parts[0])
            clean_tag = database.normalize_handle(parts[1])
            database.upsert_member(x_handle=clean_tag, tg_username=clean_tg)
            count += 1

    await message.reply_text(
        f"✅ Successfully linked <b>{count}</b> member(s) in bulk!\n"
        f"View all members with <code>/list</code>.",
        parse_mode=ParseMode.HTML
    )


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
