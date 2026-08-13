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

# Prevent duplicate join processing
processing_requests: set[tuple[int, int]] = set()


# ============================================================
# CONFIG LOAD
# ============================================================

async def load_config() -> None:
    global config

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
            "Add your BotFather token."
        )

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

    # Always enforce your owner ID.
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


async def register_chat(
    chat_id: int,
    title: str | None,
    chat_type: str,
    username: str | None = None,
) -> None:

    key = chat_key(chat_id)

    old = config["channels"].get(
        key,
        {},
    )

    config["channels"][key] = {
        "id": chat_id,
        "title": (
            title
            or old.get("title")
            or "Unknown"
        ),
        "type": chat_type,
        "username": username,
    }

    await save_config()

    logger.info(
        "CHAT REGISTERED | %s | %s | %s",
        title,
        chat_id,
        chat_type,
    )


async def unregister_chat(
    chat_id: int,
) -> None:

    key = chat_key(chat_id)

    if key in config["channels"]:

        removed = config["channels"].pop(
            key
        )

        await save_config()

        logger.info(
            "CHAT REMOVED | %s | %s",
            removed.get("title"),
            chat_id,
        )


# ============================================================
# AUTH HELPER
# ============================================================

async def require_owner(
    message: Message,
) -> bool:

    user = message.from_user

    if not user:
        return False

    if not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return False

    return True


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
) -> None:

    if not await require_owner(message):
        return

    await message.answer(
        "👑 <b>Personal Multi-Channel Bot V2</b>\n\n"
        "🟢 <b>Bot is working.</b>\n\n"
        "Bot automatically handles every "
        "channel/group where it is administrator.\n\n"
        "<b>Features:</b>\n"
        "✅ Auto join-request approval\n"
        "✅ Join welcome message\n"
        "✅ Multiple channels/groups\n"
        "✅ Leave detection\n"
        "✅ Rejoin message where Telegram allows DM\n"
        "✅ Forwarded-tag remover\n"
        "✅ Render/UptimeRobot health server\n\n"
        "<b>Commands:</b>\n"
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

    if not await require_owner(message):
        return

    await message.answer(
        "👑 <b>PERSONAL BOT V2</b>\n\n"

        "<b>Automatic:</b>\n"
        "✅ Multiple channels\n"
        "✅ Multiple groups\n"
        "✅ Auto join approval\n"
        "✅ Join welcome DM\n"
        "✅ Leave detection\n"
        "✅ Rejoin notification where possible\n"
        "✅ Forwarded-tag remover\n"
        "✅ Render health server\n\n"

        "<b>Commands:</b>\n"
        "/status - Bot status\n"
        "/channels - Managed channels/groups\n"
        "/help - Help\n\n"

        "<b>Forward Tag Remover:</b>\n"
        "Bot ko koi forwarded message private chat me "
        "send karo. Bot us message ko copy karega "
        "without the normal forwarded header.",
        parse_mode="HTML",
    )


# ============================================================
# /STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(
    message: Message,
) -> None:

    if not await require_owner(message):
        return

    await message.answer(
        "<b>⚙️ BOT STATUS</b>\n\n"
        "🟢 Telegram: Running\n"
        "🟢 Health server: Running\n"
        f"👑 Owner ID: "
        f"<code>{OWNER_ID}</code>\n"
        f"📢 Managed chats: "
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

    if not await require_owner(message):
        return

    chats = list(
        config["channels"].values()
    )

    if not chats:

        await message.answer(
            "📢 <b>No managed channels/groups.</b>\n\n"
            "Bot ko kisi channel/group me administrator "
            "banao. Bot automatically register karega.",
            parse_mode="HTML",
        )

        return

    lines = [
        "📢 <b>MANAGED CHATS</b>"
    ]

    for index, chat in enumerate(
        chats,
        start=1,
    ):

        title = chat.get(
            "title",
            "Unknown",
        )

        chat_id = chat.get(
            "id",
            "Unknown",
        )

        chat_type = chat.get(
            "type",
            "Unknown",
        )

        lines.append(
            f"\n<b>{index}. {title}</b>\n"
            f"Type: <code>{chat_type}</code>\n"
            f"ID: <code>{chat_id}</code>"
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

    processing_requests.add(key)

    try:

        logger.info(
            "JOIN REQUEST | %s | %s | %s",
            user.full_name,
            user.id,
            chat.title,
        )

        # ----------------------------------------------------
        # Auto-register channel/group
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
                    "JOIN APPROVED | %s | %s",
                    user.id,
                    chat.title,
                )

                break

            except TelegramRetryAfter as e:

                logger.warning(
                    "Rate limited. Waiting %s seconds.",
                    e.retry_after,
                )

                await asyncio.sleep(
                    e.retry_after
                )

            except TelegramNetworkError as e:

                logger.warning(
                    "Network error while approving: %s",
                    e,
                )

                await asyncio.sleep(
                    2 + attempt
                )

            except TelegramBadRequest as e:

                logger.error(
                    "Approval failed: %s",
                    e,
                )

                break

        if not approved:
            return

        # ----------------------------------------------------
        # JOIN WELCOME
        #
        # user_chat_id is supplied with ChatJoinRequest.
        # ----------------------------------------------------

        target_chat_id = request.user_chat_id

        if not target_chat_id:

            logger.warning(
                "No user_chat_id for user %s",
                user.id,
            )

            return

        try:

            await request.bot.send_message(
                chat_id=target_chat_id,
                text=(
                    f"🎉 <b>Thanks for joining "
                    f"{chat.title}!</b>\n\n"
                    "❤️ Welcome to the channel."
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
                "Telegram blocked welcome DM "
                "for user %s.",
                user.id,
            )

        except TelegramBadRequest as e:

            logger.warning(
                "Welcome DM failed: %s",
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
            "BOT IS ADMIN | %s | %s",
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

        await unregister_chat(
            chat.id
        )

        logger.info(
            "BOT REMOVED | %s | %s",
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

    # Only process registered chats
    if not get_managed_chat(chat.id):
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
        "USER LEFT | %s | %s | %s",
        user.full_name,
        user.id,
        chat.title,
    )

    # --------------------------------------------------------
    # IMPORTANT TELEGRAM LIMITATION
    #
    # We cannot magically DM every user after they leave.
    # A bot needs an existing/private chat it is allowed to
    # message. Join-request user_chat_id is intended for the
    # join-request interaction, not permanent future access.
    # --------------------------------------------------------

    try:

        await event.bot.send_message(
            chat_id=user.id,
            text=(
                f"👋 <b>You left {chat.title}</b>\n\n"
                "Agar aap dobara join karna chahte hain, "
                "channel/group ke invite link se rejoin karein."
            ),
            parse_mode="HTML",
        )

        logger.info(
            "LEAVE DM SENT | %s | %s",
            user.id,
            chat.title,
        )

    except TelegramForbiddenError:

        logger.info(
            "Cannot DM user %s after leaving %s.",
            user.id,
            chat.title,
        )

    except TelegramBadRequest as e:

        logger.info(
            "Leave DM unavailable for %s: %s",
            user.id,
            e,
        )


# ============================================================
# FORWARDED TAG REMOVER
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and is_owner(message.from_user.id)
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

    except TelegramBadRequest as e:

        logger.error(
            "Forward copy failed: %s",
            e,
        )

        await message.answer(
            "❌ Forwarded message copy nahi ho saka."
        )

    except Exception as e:

        logger.exception(
            "Forward remover error: %s",
            e,
        )


# ============================================================
# UNAUTHORIZED HANDLER
#
# IMPORTANT:
# This is AFTER ALL COMMAND HANDLERS.
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and not is_owner(message.from_user.id)
)
async def unauthorized_handler(
    message: Message,
) -> None:

    await message.answer(
        "⛔ Only admin can access this bot."
    )


# ============================================================
# GENERIC OWNER HANDLER
#
# IMPORTANT:
# THIS MUST BE LAST.
# Otherwise /help /status /channels get intercepted.
# ============================================================

@dp.message(
    lambda message:
    message.from_user is not None
    and is_owner(message.from_user.id)
)
async def owner_message_handler(
    message: Message,
) -> None:

    # Forwarded messages are already handled above.
    if message.forward_origin is not None:
        return

    # Commands should never reach here.
    if message.text and message.text.startswith("/"):
        return

    await message.answer(
        "ℹ️ Use /help to see available commands."
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
        "HTTP HEALTH SERVER | 0.0.0.0:%s",
        port,
    )

    return runner


# ============================================================
# MAIN
# ============================================================

async def main() -> None:

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

    bot = Bot(
        token=token
    )

    try:

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
            len(config["channels"]),
        )

        logger.info(
            "========================================"
        )

        # ----------------------------------------------------
        # Remove webhook before polling
        # ----------------------------------------------------

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        # ----------------------------------------------------
        # Render health server
        # ----------------------------------------------------

        health_runner = (
            await start_health_server()
        )

        try:

            # ------------------------------------------------
            # Polling
            # ------------------------------------------------

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

    finally:

        await bot.session.close()


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
