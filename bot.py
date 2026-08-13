from __future__ import annotations

import asyncio
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
    Message,
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

# ============================================================
# FILES
# ============================================================

CONFIG_FILE = "config.json"

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("PersonalBot")

# ============================================================
# TELEGRAM
# ============================================================

dp = Dispatcher()

# ============================================================
# CONFIG
# ============================================================

config: dict[str, Any] = {
    "bot_token": "",
    "owner_id": 8753552605,
    "channels": {},
}

# ============================================================
# RUNTIME
# ============================================================

# Users who started the bot.
started_users: set[int] = set()

# Users for whom a private chat ID is known from join requests.
user_chat_ids: dict[int, int] = {}

# Prevent duplicate join processing.
processing_requests: set[tuple[int, int]] = set()

# ============================================================
# FILE LOCK
# ============================================================

config_lock = asyncio.Lock()


# ============================================================
# LOAD CONFIG
# ============================================================

async def load_config() -> None:
    global config

    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "bot_token": "PASTE_BOT_TOKEN_HERE",
            "owner_id": 8753552605,
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
            "Put your BotFather token inside it."
        )

    async with aiofiles.open(
        CONFIG_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        content = await f.read()

    loaded = json.loads(content)

    if not isinstance(loaded, dict):
        raise RuntimeError(
            "config.json is invalid."
        )

    config = loaded

    config.setdefault(
        "owner_id",
        8753552605,
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


# ============================================================
# SAVE CONFIG
# ============================================================

async def save_config() -> None:

    async with config_lock:

        async with aiofiles.open(
            CONFIG_FILE,
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


# ============================================================
# OWNER
# ============================================================

def is_owner(
    user_id: int | None,
) -> bool:

    if user_id is None:
        return False

    try:
        return int(user_id) == int(
            config["owner_id"]
        )
    except Exception:
        return False


# ============================================================
# CHANNEL FUNCTIONS
# ============================================================

def channel_key(
    channel_id: int,
) -> str:

    return str(channel_id)


async def register_channel(
    chat_id: int,
    title: str,
    chat_type: str,
    username: str | None = None,
) -> None:

    key = channel_key(chat_id)

    existing = config["channels"].get(
        key,
        {},
    )

    config["channels"][key] = {
        "id": chat_id,
        "title": title or existing.get(
            "title",
            "Unknown",
        ),
        "type": chat_type,
        "username": username,
    }

    await save_config()

    logger.info(
        "Managed chat registered: %s | %s | %s",
        title,
        chat_id,
        chat_type,
    )


async def unregister_channel(
    chat_id: int,
) -> None:

    key = channel_key(chat_id)

    if key in config["channels"]:

        config["channels"].pop(key)

        await save_config()

        logger.info(
            "Managed chat removed: %s",
            chat_id,
        )


def get_channel(
    chat_id: int,
) -> dict[str, Any] | None:

    return config["channels"].get(
        channel_key(chat_id)
    )


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
) -> None:

    user = message.from_user

    if not user:
        return

    if not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    started_users.add(
        user.id
    )

    await message.answer(
        "👑 <b>Personal Multi-Channel Bot V2</b>\n\n"
        "🟢 Bot is working.\n\n"
        "The bot automatically handles every "
        "channel/group where it is an administrator.\n\n"
        "Commands:\n"
        "/status\n"
        "/channels\n"
        "/help",
        parse_mode="HTML",
    )


# ============================================================
# UNAUTHORIZED MESSAGE
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

    await message.answer(
        "⛔ Only admin can access this bot."
    )


# ============================================================
# FORWARDED MESSAGE HANDLER
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and is_owner(
        message.from_user.id
    )
    and message.forward_origin is not None
)
async def remove_forward_tag(
    message: Message,
) -> None:

    try:

        await message.copy_to(
            chat_id=message.chat.id
        )

        logger.info(
            "Forwarded message copied without "
            "forward header."
        )

    except TelegramBadRequest as e:

        logger.error(
            "Forward copy failed: %s",
            e,
        )

        await message.answer(
            "❌ This forwarded message "
            "could not be copied."
        )

    except Exception as e:

        logger.exception(
            "Forward remover error: %s",
            e,
        )


# ============================================================
# NORMAL OWNER MESSAGE
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

    # Forwarded messages are handled above.
    if message.forward_origin is not None:
        return

    await message.answer(
        "ℹ️ Use /help to see commands."
    )


# ============================================================
# /HELP
# ============================================================

@dp.message(Command("help"))
async def help_handler(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if not is_owner(
        message.from_user.id
    ):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    await message.answer(
        "<b>👑 Personal Bot V2</b>\n\n"

        "<b>Automatic:</b>\n"
        "✅ Multiple channels\n"
        "✅ Multiple groups\n"
        "✅ Join request approval\n"
        "✅ Join welcome message\n"
        "✅ Leave detection\n"
        "✅ Rejoin message\n"
        "✅ Forwarded-tag remover\n"

        "<b>Commands:</b>\n"
        "/status\n"
        "/channels\n"
        "/help\n\n"

        "<b>Forward remover:</b>\n"
        "Kisi forwarded message ko bot ke private "
        "chat me bhejo. Bot usko copy karke "
        "forwarded header remove karega.",
        parse_mode="HTML",
    )


# ============================================================
# /STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if not is_owner(
        message.from_user.id
    ):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    await message.answer(
        "<b>⚙️ BOT STATUS</b>\n\n"
        "🟢 Telegram: Running\n"
        "🟢 Health server: Running\n"
        f"👑 Owner: "
        f"<code>{config['owner_id']}</code>\n"
        f"📢 Managed chats: "
        f"<code>{len(config['channels'])}</code>\n"
        f"👤 Started users: "
        f"<code>{len(started_users)}</code>\n"
        f"💬 Known user chats: "
        f"<code>{len(user_chat_ids)}</code>",
        parse_mode="HTML",
    )


# ============================================================
# /CHANNELS
# ============================================================

@dp.message(Command("channels"))
async def channels_handler(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if not is_owner(
        message.from_user.id
    ):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    chats = list(
        config["channels"].values()
    )

    if not chats:

        await message.answer(
            "📢 <b>No managed channels/groups yet.</b>\n\n"
            "Bot ko administrator banao.",
            parse_mode="HTML",
        )

        return

    lines = [
        "<b>📢 MANAGED CHATS</b>\n"
    ]

    for index, chat in enumerate(
        chats,
        start=1,
    ):

        chat_id = chat.get(
            "id",
            "Unknown",
        )

        title = chat.get(
            "title",
            "Unknown",
        )

        chat_type = chat.get(
            "type",
            "unknown",
        )

        lines.append(
            f"{index}. <b>{title}</b>\n"
            f"   Type: <code>{chat_type}</code>\n"
            f"   ID: <code>{chat_id}</code>"
        )

    await message.answer(
        "\n\n".join(lines),
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

    processing_requests.add(key)

    try:

        # ----------------------------------------------------
        # Register channel/group automatically.
        # ----------------------------------------------------

        await register_channel(
            chat_id=chat.id,
            title=chat.title,
            chat_type=chat.type,
            username=chat.username,
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # Telegram provides user_chat_id specifically with
        # ChatJoinRequest.
        # ----------------------------------------------------

        if request.user_chat_id:

            user_chat_ids[
                user.id
            ] = request.user_chat_id

        # ----------------------------------------------------
        # APPROVE
        # ----------------------------------------------------

        try:

            await request.approve()

            logger.info(
                "JOIN APPROVED | %s | %s | %s",
                user.full_name,
                user.id,
                chat.title,
            )

        except TelegramRetryAfter as e:

            logger.warning(
                "Telegram rate limit. "
                "Waiting %s seconds.",
                e.retry_after,
            )

            await asyncio.sleep(
                e.retry_after
            )

            await request.approve()

        except TelegramBadRequest as e:

            logger.error(
                "Join approval failed: %s",
                e,
            )

            return

        # ----------------------------------------------------
        # WELCOME MESSAGE
        # ----------------------------------------------------

        # Use user_chat_id from the join request.
        target_chat_id = (
            request.user_chat_id
        )

        if not target_chat_id:

            logger.warning(
                "No user_chat_id available "
                "for %s.",
                user.id,
            )

            return

        try:

            await request.bot.send_message(
                chat_id=target_chat_id,
                text=(
                    f"🎉 <b>Thanks for joining "
                    f"{chat.title}!</b>\n\n"
                    "❤️ Welcome!"
                ),
                parse_mode="HTML",
            )

            logger.info(
                "WELCOME SENT | %s | %s",
                user.id,
                chat.title,
            )

        except TelegramForbiddenError:

            logger.warning(
                "Welcome DM forbidden for %s.",
                user.id,
            )

        except TelegramBadRequest as e:

            logger.warning(
                "Welcome DM failed for %s: %s",
                user.id,
                e,
            )

    finally:

        processing_requests.discard(key)


# ============================================================
# MEMBER UPDATE
# ============================================================

@dp.chat_member()
async def member_update_handler(
    event: ChatMemberUpdated,
) -> None:

    chat = event.chat

    # --------------------------------------------------------
    # Only channels / groups / supergroups
    # --------------------------------------------------------

    if chat.type not in {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return

    # --------------------------------------------------------
    # If this chat isn't registered yet, ignore it.
    # --------------------------------------------------------

    managed = get_channel(
        chat.id
    )

    if not managed:
        return

    old_status = (
        event.old_chat_member.status
    )

    new_status = (
        event.new_chat_member.status
    )

    user = event.new_chat_member.user

    # --------------------------------------------------------
    # MEMBER -> LEFT/KICKED
    # --------------------------------------------------------

    was_member = old_status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.RESTRICTED,
    }

    now_left = new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }

    if not was_member or not now_left:
        return

    # Don't process the bot itself.
    if user.is_bot:
        return

    logger.info(
        "USER LEFT | %s | %s | %s",
        user.full_name,
        user.id,
        chat.title,
    )

    # --------------------------------------------------------
    # We need a private chat identifier.
    # --------------------------------------------------------

    target_chat_id = user_chat_ids.get(
        user.id
    )

    if not target_chat_id:

        logger.info(
            "No known private chat for user %s. "
            "Cannot send rejoin DM.",
            user.id,
        )

        return

    # --------------------------------------------------------
    # CREATE REJOIN LINK
    # --------------------------------------------------------

    invite_link: str | None = None

    try:

        invite = (
            await event.bot.create_chat_invite_link(
                chat_id=chat.id,
                name="Rejoin",
                creates_join_request=True,
            )
        )

        invite_link = invite.invite_link

    except TelegramBadRequest as e:

        logger.warning(
            "Could not create rejoin link "
            "for %s: %s",
            chat.id,
            e,
        )

    # --------------------------------------------------------
    # SEND REJOIN MESSAGE
    # --------------------------------------------------------

    try:

        if invite_link:

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔗 Rejoin",
                            url=invite_link,
                        )
                    ]
                ]
            )

            await event.bot.send_message(
                chat_id=target_chat_id,
                text=(
                    f"👋 <b>You left "
                    f"{chat.title}</b>\n\n"
                    "Aap dobara channel/group join "
                    "karna chahte hain to neeche "
                    "button par click karein."
                ),
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        else:

            await event.bot.send_message(
                chat_id=target_chat_id,
                text=(
                    f"👋 <b>You left "
                    f"{chat.title}</b>."
                ),
                parse_mode="HTML",
            )

        logger.info(
            "REJOIN MESSAGE SENT | %s | %s",
            user.id,
            chat.title,
        )

    except TelegramForbiddenError:

        logger.warning(
            "Cannot DM user %s.",
            user.id,
        )

    except TelegramBadRequest as e:

        logger.warning(
            "Rejoin message failed: %s",
            e,
        )


# ============================================================
# BOT ADDED / REMOVED
# ============================================================

@dp.my_chat_member()
async def my_chat_member_handler(
    event: ChatMemberUpdated,
) -> None:

    chat = event.chat

    if chat.type not in {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return

    new_status = (
        event.new_chat_member.status
    )

    # --------------------------------------------------------
    # BOT BECAME ADMIN
    # --------------------------------------------------------

    if new_status == ChatMemberStatus.ADMINISTRATOR:

        await register_channel(
            chat_id=chat.id,
            title=chat.title,
            chat_type=chat.type,
            username=chat.username,
        )

        logger.info(
            "BOT ADMIN ADDED | %s | %s",
            chat.title,
            chat.id,
        )

    # --------------------------------------------------------
    # BOT LEFT / REMOVED
    # --------------------------------------------------------

    elif new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }:

        await unregister_channel(
            chat.id
        )

        logger.info(
            "BOT REMOVED | %s | %s",
            chat.title,
            chat.id,
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


async def status_http_handler(
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


async def start_health_server() -> (
    web.AppRunner
):

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
        status_http_handler,
    )

    runner = web.AppRunner(app)

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
        "Health server running on "
        "0.0.0.0:%s",
        port,
    )

    return runner


# ============================================================
# MAIN
# ============================================================

async def main() -> None:

    await load_config()

    token = config.get(
        "bot_token"
    )

    if (
        not token
        or token == "PASTE_BOT_TOKEN_HERE"
    ):

        raise RuntimeError(
            "Add BotFather token in config.json."
        )

    # --------------------------------------------------------
    # Telegram bot
    # --------------------------------------------------------

    bot = Bot(token=token)

    me = await bot.get_me()

    logger.info(
        "===================================="
    )

    logger.info(
        "BOT STARTED"
    )

    logger.info(
        "Username: @%s",
        me.username,
    )

    logger.info(
        "Bot ID: %s",
        me.id,
    )

    logger.info(
        "Owner ID: %s",
        config["owner_id"],
    )

    logger.info(
        "Managed chats: %s",
        len(config["channels"]),
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # Remove webhook so polling works.
    # --------------------------------------------------------

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    # --------------------------------------------------------
    # Start Render health server.
    # --------------------------------------------------------

    health_runner = (
        await start_health_server()
    )

    try:

        # ----------------------------------------------------
        # IMPORTANT:
        # chat_member must be explicitly requested.
        # chat_join_request is also requested.
        # ----------------------------------------------------

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

        await health_runner.cleanup()

        await bot.session.close()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped."
        )
