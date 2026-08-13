from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import aiofiles

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
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
USERS_FILE = "users.json"

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("PersonalMultiChannelBot")

# ============================================================
# TELEGRAM
# ============================================================

dp = Dispatcher()

# ============================================================
# RUNTIME DATA
# ============================================================

config: dict[str, Any] = {
    "bot_token": "",
    "owner_id": 8753552605,
    "channels": [],
}

started_users: set[int] = set()

# Prevent duplicate processing in some Telegram update situations.
processing_join_requests: set[tuple[int, int]] = set()


# ============================================================
# CONFIG LOAD
# ============================================================

async def load_config() -> None:
    global config

    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "bot_token": "PASTE_YOUR_BOT_TOKEN_HERE",
            "owner_id": 8753552605,
            "channels": [],
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

    async with aiofiles.open(
        CONFIG_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        content = await f.read()

    loaded = json.loads(content)

    if not isinstance(loaded, dict):
        raise RuntimeError("Invalid config.json")

    config = loaded

    # Safety defaults
    config.setdefault("owner_id", 8753552605)
    config.setdefault("channels", [])

    if not isinstance(config["channels"], list):
        config["channels"] = []


# ============================================================
# CONFIG SAVE
# ============================================================

async def save_config() -> None:
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
# USERS LOAD
# ============================================================

async def load_users() -> None:
    global started_users

    if not os.path.exists(USERS_FILE):

        async with aiofiles.open(
            USERS_FILE,
            "w",
            encoding="utf-8",
        ) as f:
            await f.write(
                json.dumps(
                    {"users": []},
                    indent=4,
                )
            )

        started_users = set()
        return

    try:

        async with aiofiles.open(
            USERS_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            content = await f.read()

        data = json.loads(content)

        users = data.get("users", [])

        started_users = {
            int(user_id)
            for user_id in users
        }

    except Exception as e:

        logger.error(
            "Could not load users.json: %s",
            e,
        )

        started_users = set()


# ============================================================
# USERS SAVE
# ============================================================

async def save_users() -> None:

    async with aiofiles.open(
        USERS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        await f.write(
            json.dumps(
                {
                    "users": sorted(
                        list(started_users)
                    )
                },
                indent=4,
            )
        )


# ============================================================
# OWNER CHECK
# ============================================================

def is_owner(user_id: int | None) -> bool:

    if user_id is None:
        return False

    try:
        return int(user_id) == int(
            config["owner_id"]
        )
    except Exception:
        return False


# ============================================================
# CHANNEL HELPERS
# ============================================================

def get_managed_channel(
    channel_id: int,
) -> dict[str, Any] | None:

    for channel in config.get("channels", []):

        try:

            if int(channel["id"]) == int(channel_id):
                return channel

        except Exception:
            continue

    return None


async def add_channel(
    channel_id: int,
    title: str,
    username: str | None = None,
) -> bool:

    existing = get_managed_channel(channel_id)

    if existing:

        # Update information if Telegram gives newer title.
        existing["title"] = title

        if username:
            existing["username"] = username

        await save_config()

        return False

    channel_data = {
        "id": int(channel_id),
        "title": title,
        "username": username,
    }

    config.setdefault("channels", []).append(
        channel_data
    )

    await save_config()

    logger.info(
        "New channel added: %s (%s)",
        title,
        channel_id,
    )

    return True


async def remove_channel(
    channel_id: int,
) -> bool:

    channels = config.get("channels", [])

    new_channels = []

    removed = False

    for channel in channels:

        try:

            if int(channel["id"]) == int(channel_id):
                removed = True
                continue

        except Exception:
            pass

        new_channels.append(channel)

    if removed:

        config["channels"] = new_channels

        await save_config()

    return removed


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

    # --------------------------------------------------------
    # PERSONAL BOT
    # --------------------------------------------------------

    if not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    if user.id not in started_users:

        started_users.add(user.id)

        await save_users()

    await message.answer(
        "👑 <b>Personal Multi-Channel Bot</b>\n\n"
        "✅ You are authorized.\n\n"
        "Bot automatically handles every channel "
        "where it is an administrator.\n\n"
        "Commands:\n"
        "/status\n"
        "/channels\n"
        "/removechannel\n"
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

    user = message.from_user

    if not user or not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    await message.answer(
        "<b>👑 Personal Multi-Channel Bot</b>\n\n"

        "<b>Automatic features:</b>\n"
        "✅ Join request auto approval\n"
        "✅ Joining thank-you DM\n"
        "✅ Leave detection\n"
        "✅ Rejoin message\n"
        "✅ Forwarded-tag remover\n"
        "✅ Multiple channel support\n\n"

        "<b>Commands:</b>\n"
        "/status - Bot status\n"
        "/channels - Managed channels\n"
        "/removechannel ID - Remove channel\n"
        "/help - Help\n\n"

        "<b>Forwarded tag remover:</b>\n"
        "Forwarded message bot ko send karo. "
        "Bot usko copy karke forwarded header remove karega.",
        parse_mode="HTML",
    )


# ============================================================
# /STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(
    message: Message,
) -> None:

    user = message.from_user

    if not user or not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    channels = config.get("channels", [])

    await message.answer(
        "<b>⚙️ BOT STATUS</b>\n\n"
        "🟢 Status: Running\n"
        f"👑 Owner ID: <code>{config['owner_id']}</code>\n"
        f"📢 Managed Channels: <code>{len(channels)}</code>\n"
        f"👤 Bot Users: <code>{len(started_users)}</code>",
        parse_mode="HTML",
    )


# ============================================================
# /CHANNELS
# ============================================================

@dp.message(Command("channels"))
async def channels_handler(
    message: Message,
) -> None:

    user = message.from_user

    if not user or not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    channels = config.get("channels", [])

    if not channels:

        await message.answer(
            "📢 <b>No channels detected yet.</b>\n\n"
            "Bot ko kisi private channel me administrator "
            "banao aur ek join request generate karo.",
            parse_mode="HTML",
        )

        return

    lines = [
        "<b>📢 MANAGED CHANNELS</b>\n"
    ]

    for index, channel in enumerate(
        channels,
        start=1,
    ):

        title = channel.get(
            "title",
            "Unknown",
        )

        channel_id = channel.get(
            "id",
            "Unknown",
        )

        lines.append(
            f"{index}. <b>{title}</b>\n"
            f"   🆔 <code>{channel_id}</code>"
        )

    await message.answer(
        "\n\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# /REMOVECHANNEL
# ============================================================

@dp.message(Command("removechannel"))
async def remove_channel_handler(
    message: Message,
) -> None:

    user = message.from_user

    if not user or not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:

        await message.answer(
            "Usage:\n"
            "<code>/removechannel -1001234567890</code>",
            parse_mode="HTML",
        )

        return

    try:

        channel_id = int(
            parts[1].strip()
        )

    except ValueError:

        await message.answer(
            "❌ Invalid channel ID."
        )

        return

    channel = get_managed_channel(
        channel_id
    )

    if not channel:

        await message.answer(
            "❌ This channel is not in the bot's list."
        )

        return

    removed = await remove_channel(
        channel_id
    )

    if removed:

        await message.answer(
            "🗑️ <b>Channel removed.</b>\n\n"
            f"📢 {channel.get('title', 'Unknown')}\n"
            f"🆔 <code>{channel_id}</code>\n\n"
            "Bot is still admin there, but it will "
            "no longer process that channel.",
            parse_mode="HTML",
        )

    else:

        await message.answer(
            "❌ Could not remove channel."
        )


# ============================================================
# JOIN REQUEST
# ============================================================

@dp.chat_join_request()
async def join_request_handler(
    request: ChatJoinRequest,
) -> None:

    channel = request.chat
    user = request.from_user

    request_key = (
        channel.id,
        user.id,
    )

    # --------------------------------------------------------
    # DUPLICATE PROTECTION
    # --------------------------------------------------------

    if request_key in processing_join_requests:
        return

    processing_join_requests.add(
        request_key
    )

    try:

        # ----------------------------------------------------
        # AUTOMATICALLY ADD CHANNEL
        # ----------------------------------------------------

        await add_channel(
            channel_id=channel.id,
            title=channel.title,
            username=channel.username,
        )

        # ----------------------------------------------------
        # APPROVE REQUEST
        # ----------------------------------------------------

        try:

            await request.approve()

            logger.info(
                "Approved join request: "
                "%s (%s) -> %s (%s)",
                user.full_name,
                user.id,
                channel.title,
                channel.id,
            )

        except TelegramBadRequest as e:

            logger.error(
                "Join request approval failed "
                "for %s: %s",
                user.id,
                e,
            )

            return

        # ----------------------------------------------------
        # THANK-YOU MESSAGE
        # ----------------------------------------------------

        if user.id not in started_users:

            logger.info(
                "Cannot DM %s because user "
                "has not started the bot.",
                user.id,
            )

            return

        try:

            await request.bot.send_message(
                chat_id=user.id,
                text=(
                    f"🎉 <b>Thanks for joining "
                    f"{channel.title}!</b>\n\n"
                    "❤️ Welcome to the channel."
                ),
                parse_mode="HTML",
            )

        except TelegramForbiddenError:

            logger.info(
                "User %s blocked the bot.",
                user.id,
            )

        except TelegramBadRequest as e:

            logger.warning(
                "Thank-you DM failed for %s: %s",
                user.id,
                e,
            )

    finally:

        processing_join_requests.discard(
            request_key
        )


# ============================================================
# USER LEFT CHANNEL
# ============================================================

@dp.chat_member()
async def member_update_handler(
    event: ChatMemberUpdated,
) -> None:

    # --------------------------------------------------------
    # Only process channels already detected.
    # --------------------------------------------------------

    channel = get_managed_channel(
        event.chat.id
    )

    if not channel:
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    user = event.from_user

    # --------------------------------------------------------
    # We only care about actual members leaving.
    # --------------------------------------------------------

    previous_member = old_status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.RESTRICTED,
    }

    now_left = new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }

    if not previous_member or not now_left:
        return

    logger.info(
        "User left %s: %s (%s)",
        event.chat.title,
        user.full_name,
        user.id,
    )

    # --------------------------------------------------------
    # Telegram restriction:
    # Bot cannot initiate a private conversation with a user
    # who has never started the bot.
    # --------------------------------------------------------

    if user.id not in started_users:

        logger.info(
            "Rejoin DM cannot be sent to %s "
            "because the user never started the bot.",
            user.id,
        )

        return

    # --------------------------------------------------------
    # CREATE REJOIN REQUEST LINK
    # --------------------------------------------------------

    invite_url: str | None = None

    try:

        invite = await event.bot.create_chat_invite_link(
            chat_id=event.chat.id,
            creates_join_request=True,
            name="Rejoin",
        )

        invite_url = invite.invite_link

    except TelegramBadRequest as e:

        logger.warning(
            "Could not create invite link "
            "for %s: %s",
            event.chat.id,
            e,
        )

    except Exception as e:

        logger.exception(
            "Invite link error: %s",
            e,
        )

    # --------------------------------------------------------
    # REJOIN MESSAGE
    # --------------------------------------------------------

    try:

        if invite_url:

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔗 Rejoin Channel",
                            url=invite_url,
                        )
                    ]
                ]
            )

            text = (
                f"👋 <b>You left "
                f"{event.chat.title}</b>\n\n"
                "Agar aap dobara channel join karna "
                "chahte hain, neeche button par click karein."
            )

            await event.bot.send_message(
                chat_id=user.id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        else:

            await event.bot.send_message(
                chat_id=user.id,
                text=(
                    f"👋 <b>You left "
                    f"{event.chat.title}</b>\n\n"
                    "Aap dobara channel join kar sakte hain."
                ),
                parse_mode="HTML",
            )

    except TelegramForbiddenError:

        logger.info(
            "User %s blocked the bot.",
            user.id,
        )

    except TelegramBadRequest as e:

        logger.warning(
            "Rejoin message failed for %s: %s",
            user.id,
            e,
        )

    except Exception as e:

        logger.exception(
            "Unexpected rejoin error: %s",
            e,
        )


# ============================================================
# FORWARDED TAG REMOVER
# ============================================================

@dp.message()
async def forwarded_message_handler(
    message: Message,
) -> None:

    user = message.from_user

    if not user:
        return

    # --------------------------------------------------------
    # PERSONAL ACCESS
    # --------------------------------------------------------

    if not is_owner(user.id):

        await message.answer(
            "⛔ Only admin can access this bot."
        )

        return

    # --------------------------------------------------------
    # SAVE OWNER AS STARTED USER
    # --------------------------------------------------------

    if user.id not in started_users:

        started_users.add(user.id)

        await save_users()

    # --------------------------------------------------------
    # FORWARDED MESSAGE
    # --------------------------------------------------------

    if message.forward_origin is not None:

        try:

            await message.copy_to(
                chat_id=message.chat.id
            )

            logger.info(
                "Forwarded message copied "
                "without forwarding header."
            )

            return

        except TelegramBadRequest as e:

            logger.warning(
                "Could not copy forwarded message: %s",
                e,
            )

            await message.answer(
                "❌ This message could not be copied."
            )

            return

        except Exception as e:

            logger.exception(
                "Forward remover error: %s",
                e,
            )

            return

    # --------------------------------------------------------
    # NORMAL MESSAGE
    # --------------------------------------------------------

    await message.answer(
        "ℹ️ Use /help to see available commands."
    )


# ============================================================
# BOT ADDED / REMOVED FROM CHANNEL
# ============================================================

@dp.my_chat_member()
async def bot_chat_member_handler(
    event: ChatMemberUpdated,
) -> None:

    chat = event.chat

    # --------------------------------------------------------
    # Only channels
    # --------------------------------------------------------

    if chat.type != "channel":
        return

    new_status = event.new_chat_member.status

    # --------------------------------------------------------
    # BOT BECAME ADMIN
    # --------------------------------------------------------

    if new_status == ChatMemberStatus.ADMINISTRATOR:

        try:

            await add_channel(
                channel_id=chat.id,
                title=chat.title,
                username=chat.username,
            )

            logger.info(
                "Bot added as admin to channel: "
                "%s (%s)",
                chat.title,
                chat.id,
            )

        except Exception as e:

            logger.exception(
                "Could not register channel: %s",
                e,
            )

    # --------------------------------------------------------
    # BOT REMOVED / LEFT
    # --------------------------------------------------------

    elif new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }:

        removed = await remove_channel(
            chat.id
        )

        if removed:

            logger.info(
                "Removed channel because "
                "bot is no longer admin: %s (%s)",
                chat.title,
                chat.id,
            )


# ============================================================
# MAIN
# ============================================================

async def main() -> None:

    await load_config()
    await load_users()

    token = config.get("bot_token")

    if (
        not token
        or token == "PASTE_YOUR_BOT_TOKEN_HERE"
    ):

        raise RuntimeError(
            "Please put your BotFather token "
            "inside config.json."
        )

    bot = Bot(token=token)

    me = await bot.get_me()

    logger.info(
        "=========================================="
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
        "Managed channels: %s",
        len(config.get("channels", [])),
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # Remove webhook
    # --------------------------------------------------------

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    # --------------------------------------------------------
    # START POLLING
    # --------------------------------------------------------

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "chat_join_request",
            "chat_member",
            "my_chat_member",
        ],
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped."
)
