"""Optional Telegram bot interface for BLAGOVA_SWEETS Content Agent."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.content_agent import ContentAgent
from app.errors import AppError
from app.logging_setup import setup_logging
from app.models import KNOWN_STYLES

logger = logging.getLogger(__name__)

STYLE_BUTTONS = list(KNOWN_STYLES)
MAX_USER_INPUT_CHARS = 6000

# Defaults for Telegram → ContentAgent (shared prompts, no Telegram-specific LLM prompt).
TELEGRAM_GENERATE_DEFAULTS: dict[str, object] = {
    "platform": "telegram",
    "goal": "product",
    "max_length": 800,
    "cta": False,
    "hashtags": False,
}


@dataclass
class DialogState:
    waiting_for: str | None = None  # content | style
    content_type: str | None = None  # url | text
    content: str | None = None
    style: str = "friendly"


@dataclass
class BotRuntime:
    agent: ContentAgent
    states: dict[int, DialogState] = field(default_factory=dict)

    def state_for(self, chat_id: int) -> DialogState:
        if chat_id not in self.states:
            self.states[chat_id] = DialogState()
        return self.states[chat_id]


def bot_token_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.bot_token)


async def run_bot(settings: Settings | None = None) -> None:
    """Start long polling. Requires BOT_TOKEN."""
    setup_logging()
    settings = settings or get_settings()
    if not settings.bot_token:
        raise AppError("BOT_TOKEN не настроен")

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    runtime = BotRuntime(agent=ContentAgent(settings=settings))

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_chat and update.message
        text = (
            "Привет! Я <b>BLAGOVA_SWEETS Content Agent</b>.\n\n"
            "Помогу быстро собрать пост для соцсетей бренда BLAGOVA_SWEETS.\n\n"
            "Команды:\n"
            "/post — сгенерировать пост\n"
            "/cancel — отменить текущий диалог"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_chat
        runtime.states.pop(update.effective_chat.id, None)
        await update.message.reply_text("Диалог отменён. Чтобы начать снова: /post")

    async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_chat and update.message
        state = runtime.state_for(update.effective_chat.id)
        state.waiting_for = "content"
        state.content = None
        state.content_type = None
        state.style = "friendly"
        await update.message.reply_text(
            "Пришлите URL страницы или текст для поста.\n"
            "После этого можно выбрать стиль."
        )

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_chat and update.message and update.message.text
        chat_id = update.effective_chat.id
        state = runtime.state_for(chat_id)
        text = update.message.text.strip()

        if state.waiting_for != "content":
            await update.message.reply_text("Чтобы начать генерацию, отправьте /post")
            return

        if len(text) > MAX_USER_INPUT_CHARS:
            await update.message.reply_text(
                f"Слишком длинный текст. Максимум {MAX_USER_INPUT_CHARS} символов."
            )
            return

        if text.lower().startswith(("http://", "https://")):
            state.content_type = "url"
            state.content = text
        else:
            state.content_type = "text"
            state.content = text

        state.waiting_for = "style"
        keyboard = [
            [InlineKeyboardButton(s, callback_data=f"style:{s}") for s in STYLE_BUTTONS[:4]],
            [InlineKeyboardButton(s, callback_data=f"style:{s}") for s in STYLE_BUTTONS[4:]],
            [InlineKeyboardButton("По умолчанию (friendly)", callback_data="style:friendly")],
        ]
        await update.message.reply_text(
            "Выберите стиль поста:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def on_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        assert query and query.data and update.effective_chat
        await query.answer()
        chat_id = update.effective_chat.id
        state = runtime.state_for(chat_id)

        if state.waiting_for != "style" or not state.content or not state.content_type:
            await query.edit_message_text("Сначала отправьте /post и исходный текст/URL.")
            return

        style = query.data.split(":", 1)[1]
        state.style = style
        state.waiting_for = None
        await query.edit_message_text(f"Стиль: {style}\nГенерирую пост…")

        try:
            result = await asyncio.to_thread(
                runtime.agent.generate_post,
                url=state.content if state.content_type == "url" else None,
                text=state.content if state.content_type == "text" else None,
                style=style,
                created_by_role="telegram",
                **TELEGRAM_GENERATE_DEFAULTS,
            )
        except AppError as exc:
            await context.bot.send_message(chat_id=chat_id, text=f"Ошибка: {exc.message}")
            return
        except Exception:  # noqa: BLE001
            logger.exception("Telegram generation failed")
            await context.bot.send_message(chat_id=chat_id, text="Ошибка: произошёл внутренний сбой")
            return
        finally:
            runtime.states.pop(chat_id, None)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{result.post}\n\n—\nСимволов: {result.length}",
        )

    application = Application.builder().token(settings.bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("post", post_cmd))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(on_style, pattern=r"^style:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Telegram bot starting")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


def main() -> None:
    setup_logging()
    settings = get_settings()
    if not bot_token_configured(settings):
        print("BOT_TOKEN не настроен — Telegram-бот не запущен.")
        raise SystemExit(1)
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()
