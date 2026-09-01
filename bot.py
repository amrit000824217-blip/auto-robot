from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from typing import Any

import aiofiles
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = "config.json"

# Your Telegram ID
OWNER_ID = 8753552605

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("PersonalBotV2")

dp = Dispatcher()

config: dict[str, Any] = {
    "bot_token": "",
    "owner_id": OWNER_ID,
    "channels": {},
}

config_lock = asyncio.Lock()

# Prevent duplicate join-request processing
processing_requests: set[tuple[int, int]] = set()


# ============================================================
# HTML HELPERS
# ============================================================

def safe_html(value: Any) -> str:
    """
    Safely escape text before putting it inside HTML Telegram
    messages.
    """
    if value is None:
        return ""

    return html.escape(
        str(value),
        quote=False,
    )


# ============================================================
# CONFIG LOAD
# ============================================================

async def load_config() -> None:
    global config

    # --------------------------------------------------------
    # CREATE CONFIG IF MISSING
    # --------------------------------------------------------

    if not os.path.exists(CONFIG_FILE):

        default_config = {
            "bot_token": "PASTE_BOT_TOKEN_HERE",
            "owner_id": OWNER_ID,
            "channels": {},
        }

        async with aiofiles.open(
            CONFIG_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            await f.write(
                json.dumps(
                    default_config,
                    indent=4,
                    ensure_ascii=False,
                )
            )

        raise RuntimeError(
            "config.json created. "
            "Add your BotFather token and restart the bot."
        )

    # --------------------------------------------------------
    # READ CONFIG
    # --------------------------------------------------------

    async with aiofiles.open(
        CONFIG_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        raw = await f.read()

    try:

        loaded = json.loads(raw)

    except json.JSONDecodeError as e:

        raise RuntimeError(
            f"Invalid config.json: {e}"
        )

    if not isinstance(loaded, dict):

        raise RuntimeError(
            "config.json must contain a JSON object."
        )

    config = loaded

    # --------------------------------------------------------
    # DEFAULT VALUES
    # --------------------------------------------------------

    config.setdefault(
        "owner_id",
        OWNER_ID,
    )

    config.setdefault(
        "channels",
        {},
    )

    if not isinstance(
        config["channels"],
        dict,
    ):
        config["channels"] = {}

    # --------------------------------------------------------
    # ALWAYS USE YOUR OWNER ID
    # --------------------------------------------------------

    config["owner_id"] = OWNER_ID


# ============================================================
# CONFIG SAVE
# ============================================================

async def save_config() -> None:

    async with config_lock:

        temp_file = CONFIG_FILE + ".tmp"

        async with aiofiles.open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as f:

            await f.write(
                json.dumps(
                    config,
                    indent=4,
                    ensure_ascii=False,
                )
            )

        os.replace(
            temp_file,
            CONFIG_FILE,
        )


# ============================================================
# OWNER CHECK
# ============================================================

def is_owner(
    user_id: int | None,
) -> bool:

    if user_id is None:
        return False

    try:

        return int(user_id) == OWNER_ID

    except Exception:

        return False


async def require_owner(
    message: Message,
) -> bool:

    user = message.from_user

    if not user:
        return False

    if not is_owner(user.id):

        await message.answer(
            "⛔ <b>Access Denied</b>\n\n"
            "Only the bot administrator can use this bot.",
            parse_mode="HTML",
        )

        return False

    return True


# ============================================================
# CHAT HELPERS
# ============================================================

def chat_key(
    chat_id: int,
) -> str:

    return str(chat_id)


def get_managed_chat(
    chat_id: int,
) -> dict[str, Any] | None:

    return config["channels"].get(
        chat_key(chat_id)
    )


# ============================================================
# REGISTER CHAT
# ============================================================

async def register_chat(
    chat_id: int,
    title: str | None,
    chat_type: str,
    username: str | None = None,
    invite_link: str | None = None,
) -> None:

    key = chat_key(chat_id)

    old = config["channels"].get(
        key,
        {},
    )

    # Keep previously saved invite link
    saved_invite = old.get(
        "invite_link"
    )

    final_invite_link = (
        invite_link
        or saved_invite
    )

    config["channels"][key] = {
        "id": chat_id,
        "title": (
            title
            or old.get("title")
            or "Unknown"
        ),
        "type": chat_type,
        "username": (
            username
            or old.get("username")
        ),
        "invite_link": final_invite_link,
    }

    await save_config()

    logger.info(
        "CHAT REGISTERED | title=%s | id=%s | type=%s",
        title,
        chat_id,
        chat_type,
    )


# ============================================================
# UNREGISTER CHAT
# ============================================================

async def unregister_chat(
    chat_id: int,
) -> None:

    key = chat_key(chat_id)

    if key not in config["channels"]:
        return

    removed = config["channels"].pop(
        key
    )

    await save_config()

    logger.info(
        "CHAT REMOVED | title=%s | id=%s",
        removed.get("title"),
        chat_id,
    )


# ============================================================
# REJOIN LINK
# ============================================================

async def get_rejoin_link(
    bot: Bot,
    chat_id: int,
) -> str | None:

    chat = get_managed_chat(
        chat_id
    )

    if not chat:
        return None

    # --------------------------------------------------------
    # 1. Saved invite link
    # --------------------------------------------------------

    saved_link = chat.get(
        "invite_link"
    )

    if saved_link:

        return str(
            saved_link
        )

    # --------------------------------------------------------
    # 2. Public username
    # --------------------------------------------------------

    username = chat.get(
        "username"
    )

    if username:

        username = str(
            username
        ).lstrip("@").strip()

        if username:

            link = (
                f"https://t.me/{username}"
            )

            chat["invite_link"] = link

            await save_config()

            return link

    # --------------------------------------------------------
    # 3. Create private invite link
    # --------------------------------------------------------

    try:

        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name="Rejoin",
        )

        link = invite.invite_link

        chat["invite_link"] = link

        await save_config()

        logger.info(
            "REJOIN LINK CREATED | %s | %s",
            chat_id,
            link,
        )

        return link

    except TelegramRetryAfter as e:

        logger.warning(
            "Invite creation rate limited: %s sec",
            e.retry_after,
        )

        await asyncio.sleep(
            e.retry_after
        )

        return None

    except TelegramForbiddenError:

        logger.warning(
            "No permission to create invite link | %s",
            chat_id,
        )

        return None

    except TelegramBadRequest as e:

        logger.warning(
            "Cannot create invite link | %s | %s",
            chat_id,
            e,
        )

        return None

    except TelegramNetworkError as e:

        logger.warning(
            "Network error creating invite | %s",
            e,
        )

        return None

    except Exception as e:

        logger.exception(
            "Unexpected invite link error | %s",
            e,
        )

        return None


# ============================================================
# BUILD LEAVE KEYBOARD
# ============================================================

def build_leave_keyboard(
    rejoin_link: str | None,
) -> InlineKeyboardMarkup | None:

    if not rejoin_link:
        return None

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Rejoin",
                    url=rejoin_link,
                ),
                InlineKeyboardButton(
                    text="🏠 Open Channel",
                    url=rejoin_link,
                ),
            ]
        ]
    )

    return keyboard


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
) -> None:

    if not await require_owner(
        message
    ):
        return

    await message.answer(
        "👑 <b>PERSONAL MULTI-CHANNEL BOT V2</b>\n\n"

        "🟢 <b>System Status:</b> Online\n\n"

        "This bot automatically manages your "
        "Telegram channels and groups.\n\n"

        "✨ <b>Features</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Automatic join-request approval\n"
        "✅ Professional welcome DM\n"
        "✅ Professional leave notification\n"
        "✅ Automatic rejoin buttons\n"
        "✅ Multiple channels & groups\n"
        "✅ Bot admin detection\n"
        "✅ Leave detection\n"
        "✅ Forwarded-tag remover\n"
        "✅ Persistent JSON configuration\n"
        "✅ Render/UptimeRobot health server\n\n"

        "📌 <b>Commands</b>\n"
        "/status\n"
        "/channels\n"
        "/help",
        parse_mode="HTML",
    )


# ============================================================
# /HELP
# ============================================================

@dp.message(Command("help"))
async def help_handler(
    message: Message,
) -> None:

    if not await require_owner(
        message
    ):
        return

    await message.answer(
        "👑 <b>PERSONAL BOT V2 — HELP</b>\n\n"

        "⚙️ <b>Automatic System</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "• Multiple channels\n"
        "• Multiple groups\n"
        "• Auto join approval\n"
        "• Welcome DM\n"
        "• Leave detection\n"
        "• Professional leave DM\n"
        "• Rejoin buttons\n"
        "• Automatic invite-link handling\n"
        "• Forwarded-tag remover\n"
        "• Health server\n\n"

        "📋 <b>Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "/start — Bot information\n"
        "/status — System status\n"
        "/channels — Managed chats\n"
        "/help — Show this help\n\n"

        "📎 <b>Forwarded Message Remover</b>\n"
        "Send a forwarded message to this bot "
        "from the owner account.\n\n"
        "The bot will copy the message back "
        "without the normal forwarded header "
        "whenever Telegram allows copying it.",
        parse_mode="HTML",
    )


# ============================================================
# /STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(
    message: Message,
) -> None:

    if not await require_owner(
        message
    ):
        return

    await message.answer(
        "⚙️ <b>BOT STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🟢 Telegram: <b>Online</b>\n"
        "🟢 Health Server: <b>Online</b>\n"
        "🟢 Auto Approval: <b>Enabled</b>\n"
        "🟢 Leave Detection: <b>Enabled</b>\n"
        "🟢 Rejoin Buttons: <b>Enabled</b>\n"
        "🟢 Forward Remover: <b>Enabled</b>\n\n"

        f"👑 Owner ID: <code>{OWNER_ID}</code>\n"
        f"📢 Managed Chats: "
        f"<code>{len(config['channels'])}</code>",
        parse_mode="HTML",
    )


# ============================================================
# /CHANNELS
# ============================================================

@dp.message(Command("channels"))
async def channels_handler(
    message: Message,
) -> None:

    if not await require_owner(
        message
    ):
        return

    chats = list(
        config["channels"].values()
    )

    if not chats:

        await message.answer(
            "📢 <b>No Managed Chats</b>\n\n"
            "Add the bot as an administrator "
            "to a channel or group.\n\n"
            "It will automatically register "
            "the chat.",
            parse_mode="HTML",
        )

        return

    lines = [
        "📢 <b>MANAGED CHATS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for index, chat in enumerate(
        chats,
        start=1,
    ):

        title = safe_html(
            chat.get(
                "title",
                "Unknown",
            )
        )

        chat_id = chat.get(
            "id",
            "Unknown",
        )

        chat_type = safe_html(
            chat.get(
                "type",
                "Unknown",
            )
        )

        username = chat.get(
            "username"
        )

        invite = chat.get(
            "invite_link"
        )

        lines.append(
            f"\n<b>{index}. {title}</b>\n"
            f"Type: <code>{chat_type}</code>\n"
            f"ID: <code>{chat_id}</code>"
        )

        if username:

            lines.append(
                f"Username: "
                f"<code>@{safe_html(str(username).lstrip('@'))}</code>"
            )

        if invite:

            lines.append(
                "🔗 Rejoin link: <b>Saved</b>"
            )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# JOIN REQUEST
# ============================================================

@dp.chat_join_request()
async def join_request_handler(
    request: ChatJoinRequest,
) -> None:

    chat = request.chat
    user = request.from_user

    key = (
        chat.id,
        user.id,
    )

    if key in processing_requests:
        return

    processing_requests.add(
        key
    )

    try:

        logger.info(
            "JOIN REQUEST | user=%s | user_id=%s | chat=%s",
            user.full_name,
            user.id,
            chat.title,
        )

        # ----------------------------------------------------
        # REGISTER CHAT
        # ----------------------------------------------------

        await register_chat(
            chat_id=chat.id,
            title=chat.title,
            chat_type=chat.type,
            username=chat.username,
        )

        # ----------------------------------------------------
        # APPROVE REQUEST
        # ----------------------------------------------------

        approved = False

        for attempt in range(3):

            try:

                await request.approve()

                approved = True

                logger.info(
                    "JOIN APPROVED | user=%s | chat=%s",
                    user.id,
                    chat.title,
                )

                break

            except TelegramRetryAfter as e:

                logger.warning(
                    "Approval rate limited | waiting=%s",
                    e.retry_after,
                )

                await asyncio.sleep(
                    e.retry_after
                )

            except TelegramNetworkError as e:

                logger.warning(
                    "Approval network error | %s",
                    e,
                )

                await asyncio.sleep(
                    2 + attempt
                )

            except TelegramBadRequest as e:

                logger.error(
                    "Approval failed | %s",
                    e,
                )

                break

            except Exception as e:

                logger.exception(
                    "Unexpected approval error | %s",
                    e,
                )

                break

        if not approved:
            return

        # ----------------------------------------------------
        # WELCOME DM
        # ----------------------------------------------------

        target_chat_id = request.user_chat_id

        if not target_chat_id:

            logger.warning(
                "No user_chat_id available | user=%s",
                user.id,
            )

            return

        safe_title = safe_html(
            chat.title
            or "our channel"
        )

        safe_name = safe_html(
            user.first_name
            or user.full_name
            or "there"
        )

        welcome_text = (
            f"🎉 <b>Welcome, {safe_name}!</b>\n\n"

            f"You're now a member of "
            f"<b>{safe_title}</b>. ❤️\n\n"

            "Thank you for joining us!\n\n"

            "✨ <b>Stay connected for:</b>\n"
            "• 📢 Latest updates\n"
            "• ⚡ Fresh content\n"
            "• 🔔 Important announcements\n"
            "• 💎 Exclusive posts\n\n"

            "We're glad to have you here. 🖤"
        )

        try:

            await request.bot.send_message(
                chat_id=target_chat_id,
                text=welcome_text,
                parse_mode="HTML",
            )

            logger.info(
                "WELCOME SENT | user=%s | chat=%s",
                user.id,
                chat.title,
            )

        except TelegramForbiddenError:

            logger.warning(
                "Welcome DM blocked | user=%s",
                user.id,
            )

        except TelegramBadRequest as e:

            logger.warning(
                "Welcome DM failed | user=%s | %s",
                user.id,
                e,
            )

        except TelegramNetworkError as e:

            logger.warning(
                "Welcome DM network error | %s",
                e,
            )

    finally:

        processing_requests.discard(
            key
        )


# ============================================================
# BOT ADDED / REMOVED
# ============================================================

@dp.my_chat_member()
async def bot_chat_member_handler(
    event: ChatMemberUpdated,
) -> None:

    chat = event.chat

    if chat.type not in {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return

    old_status = (
        event.old_chat_member.status
    )

    new_status = (
        event.new_chat_member.status
    )

    # --------------------------------------------------------
    # BOT BECAME ADMIN
    # --------------------------------------------------------

    if new_status == ChatMemberStatus.ADMINISTRATOR:

        await register_chat(
            chat_id=chat.id,
            title=chat.title,
            chat_type=chat.type,
            username=chat.username,
        )

        logger.info(
            "BOT IS ADMIN | chat=%s | id=%s",
            chat.title,
            chat.id,
        )

    # --------------------------------------------------------
    # BOT LEFT / KICKED
    # --------------------------------------------------------

    elif new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }:

        await unregister_chat(
            chat.id
        )

        logger.info(
            "BOT REMOVED | chat=%s | id=%s",
            chat.title,
            chat.id,
        )


# ============================================================
# MEMBER UPDATE / LEAVE DETECTION
# ============================================================

@dp.chat_member()
async def member_update_handler(
    event: ChatMemberUpdated,
) -> None:

    chat = event.chat

    if chat.type not in {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return

    # --------------------------------------------------------
    # ONLY MANAGED CHATS
    # --------------------------------------------------------

    if not get_managed_chat(
        chat.id
    ):
        return

    old_status = (
        event.old_chat_member.status
    )

    new_status = (
        event.new_chat_member.status
    )

    user = event.new_chat_member.user

    if user.is_bot:
        return

    # --------------------------------------------------------
    # MEMBER STATUS CHECK
    # --------------------------------------------------------

    was_member = old_status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.RESTRICTED,
    }

    left_now = new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }

    if not was_member or not left_now:
        return

    logger.info(
        "USER LEFT | user=%s | user_id=%s | chat=%s",
        user.full_name,
        user.id,
        chat.title,
    )

    # --------------------------------------------------------
    # CREATE / GET REJOIN LINK
    # --------------------------------------------------------

    rejoin_link = await get_rejoin_link(
        event.bot,
        chat.id,
    )

    # --------------------------------------------------------
    # KEYBOARD
    # --------------------------------------------------------

    keyboard = build_leave_keyboard(
        rejoin_link
    )

    # --------------------------------------------------------
    # SAFE TEXT
    # --------------------------------------------------------

    safe_title = safe_html(
        chat.title
        or "our community"
    )

    safe_name = safe_html(
        user.first_name
        or user.full_name
        or "there"
    )

    # --------------------------------------------------------
    # PROFESSIONAL LEAVE MESSAGE
    # --------------------------------------------------------

    leave_text = (
        f"👋 <b>We'll Miss You, {safe_name}!</b>\n\n"

        f"📢 You have left "
        f"<b>{safe_title}</b>.\n\n"

        "We respect your decision. ❤️ "
        "However, if you left by mistake or simply "
        "changed your mind, you're always welcome "
        "to come back.\n\n"

        "✨ <b>Why rejoin?</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "• 🔔 Get the latest updates instantly\n"
        "• 📢 Stay informed about important posts\n"
        "• ⚡ Never miss new content\n"
        "• 💎 Access future updates & announcements\n"
        "• 🔐 Enjoy a simple and private experience\n\n"

        "💭 <b>Changed your mind?</b>\n"
        "No problem. You can rejoin the community "
        "whenever you want using the button below.\n\n"

        "🖤 <i>Your place is always open.</i>\n\n"

        "❤️ <b>Hope to see you again soon!</b>"
    )

    # --------------------------------------------------------
    # SEND DM
    # --------------------------------------------------------

    try:

        await event.bot.send_message(
            chat_id=user.id,
            text=leave_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        logger.info(
            "LEAVE DM SENT | user=%s | chat=%s",
            user.id,
            chat.title,
        )

    except TelegramForbiddenError:

        logger.info(
            "Cannot DM user after leaving | user=%s | chat=%s",
            user.id,
            chat.title,
        )

    except TelegramBadRequest as e:

        logger.info(
            "Leave DM unavailable | user=%s | error=%s",
            user.id,
            e,
        )

    except TelegramNetworkError as e:

        logger.warning(
            "Leave DM network error | %s",
            e,
        )

    except TelegramRetryAfter as e:

        logger.warning(
            "Leave DM rate limited | waiting=%s",
            e.retry_after,
        )

        await asyncio.sleep(
            e.retry_after
        )

    except Exception as e:

        logger.exception(
            "Leave notification error | %s",
            e,
        )


# ============================================================
# FORWARDED TAG REMOVER
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and is_owner(
        message.from_user.id
    )
    and message.forward_origin is not None
)
async def forwarded_message_handler(
    message: Message,
) -> None:

    try:

        await message.copy_to(
            chat_id=message.chat.id
        )

        logger.info(
            "FORWARD TAG REMOVED | message=%s",
            message.message_id,
        )

    except TelegramRetryAfter as e:

        logger.warning(
            "Forward copy rate limited | waiting=%s",
            e.retry_after,
        )

        await asyncio.sleep(
            e.retry_after
        )

        try:

            await message.copy_to(
                chat_id=message.chat.id
            )

        except Exception as retry_error:

            logger.error(
                "Forward retry failed | %s",
                retry_error,
            )

    except TelegramBadRequest as e:

        logger.error(
            "Forward copy failed | %s",
            e,
        )

        try:

            await message.answer(
                "❌ <b>Forwarded message copy nahi ho saka.</b>",
                parse_mode="HTML",
            )

        except Exception:
            pass

    except Exception as e:

        logger.exception(
            "Forward remover error | %s",
            e,
        )


# ============================================================
# UNAUTHORIZED HANDLER
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and not is_owner(
        message.from_user.id
    )
)
async def unauthorized_handler(
    message: Message,
) -> None:

    try:

        await message.answer(
            "⛔ <b>Access Denied</b>\n\n"
            "This bot is private and can only "
            "be controlled by its administrator.",
            parse_mode="HTML",
        )

    except Exception as e:

        logger.warning(
            "Unauthorized response failed | %s",
            e,
        )


# ============================================================
# GENERIC OWNER MESSAGE
#
# MUST REMAIN LAST
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and is_owner(
        message.from_user.id
    )
)
async def owner_message_handler(
    message: Message,
) -> None:

    # Forwarded messages handled above
    if message.forward_origin is not None:
        return

    # Commands handled above
    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    await message.answer(
        "ℹ️ <b>Bot is running.</b>\n\n"
        "Use /help to see available commands.",
        parse_mode="HTML",
    )


# ============================================================
# HEALTH SERVER
# ============================================================

async def health_handler(
    request: web.Request,
) -> web.Response:

    return web.Response(
        text="OK",
        status=200,
    )


async def health_json_handler(
    request: web.Request,
) -> web.Response:

    return web.json_response(
        {
            "status": "ok",
            "telegram": "running",
            "managed_chats": len(
                config["channels"]
            ),
        }
    )


async def start_health_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health_handler,
    )

    app.router.add_get(
        "/health",
        health_handler,
    )

    app.router.add_get(
        "/status",
        health_json_handler,
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port,
    )

    await site.start()

    logger.info(
        "HTTP HEALTH SERVER | 0.0.0.0:%s",
        port,
    )

    return runner


# ============================================================
# MAIN
# ============================================================

async def main() -> None:

    # --------------------------------------------------------
    # LOAD CONFIG
    # --------------------------------------------------------

    await load_config()

    token = str(
        config.get(
            "bot_token",
            "",
        )
    ).strip()

    if (
        not token
        or token == "PASTE_BOT_TOKEN_HERE"
    ):

        raise RuntimeError(
            "Bot token missing in config.json."
        )

    # --------------------------------------------------------
    # CREATE BOT
    # --------------------------------------------------------

    bot = Bot(
        token=token
    )

    health_runner = None

    try:

        # ----------------------------------------------------
        # TEST TELEGRAM CONNECTION
        # ----------------------------------------------------

        me = await bot.get_me()

        logger.info(
            "========================================"
        )

        logger.info(
            "PERSONAL TELEGRAM BOT V2"
        )

        logger.info(
            "Bot: @%s",
            me.username,
        )

        logger.info(
            "Bot ID: %s",
            me.id,
        )

        logger.info(
            "Owner ID: %s",
            OWNER_ID,
        )

        logger.info(
            "Managed chats: %s",
            len(
                config["channels"]
            ),
        )

        logger.info(
            "========================================"
        )

        # ----------------------------------------------------
        # REMOVE WEBHOOK
        # ----------------------------------------------------

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        logger.info(
            "Webhook removed."
        )

        # ----------------------------------------------------
        # START HEALTH SERVER
        # ----------------------------------------------------

        health_runner = (
            await start_health_server()
        )

        # ----------------------------------------------------
        # START POLLING
        # ----------------------------------------------------

        logger.info(
            "Starting Telegram polling..."
        )

        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "chat_join_request",
                "chat_member",
                "my_chat_member",
            ],
        )

    finally:

        # ----------------------------------------------------
        # HEALTH SERVER CLEANUP
        # ----------------------------------------------------

        if health_runner:

            try:

                await health_runner.cleanup()

            except Exception as e:

                logger.warning(
                    "Health server cleanup error | %s",
                    e,
                )

        # ----------------------------------------------------
        # BOT SESSION CLOSE
        # ----------------------------------------------------

        try:

            await bot.session.close()

        except Exception as e:

            logger.warning(
                "Bot session close error | %s",
                e,
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped manually."
        )

    except Exception as e:

        logger.exception(
            "BOT CRASHED | %s",
            e,
    )
