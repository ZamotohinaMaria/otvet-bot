"""
Точка входа. Запускает планировщик опроса Ozon + Telegram-бота.
"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import bot.state as st
from bot.config import MODE, POLL_INTERVAL_MINUTES, LLM_API_KEY
from bot.ozon_client import OzonClient
from bot.classifier import classify_review
from bot.llm_client import LLMClient
from bot.telegram_handler import bot, dp, send_review_to_chat
from bot.template_manager import router as template_router

# ──────────────── Логирование ────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ──────────────── Клиенты ────────────────

ozon = OzonClient()
llm = LLMClient() if LLM_API_KEY else None


# ──────────────── Опрос Ozon ────────────────

async def poll_reviews():
    """Получает новые неотвеченные отзывы и обрабатывает их."""
    logger.info("Проверяю новые отзывы...")
    reviews = ozon.get_unanswered_reviews(limit=100)
    mode = st.get_mode()
    new = 0

    for review in reviews:
        uuid = ozon.extract_uuid(review)
        if not uuid:
            continue
        if st.is_processed(uuid) or st.is_pending(uuid):
            continue

        new += 1
        template_key, proposed = classify_review(review, llm)

        if mode == "auto" and proposed:
            # Авто-режим: сразу отправляем ответ на Ozon
            success = ozon.send_reply(uuid, proposed)
            if success:
                st.mark_processed(uuid)
                await send_review_to_chat(review, template_key, proposed)
            else:
                logger.error("Не удалось отправить авто-ответ на %s", uuid)
        else:
            # Полуавто или сложный отзыв: отправляем в Telegram для ручной обработки
            await send_review_to_chat(review, template_key, proposed)
            if not proposed:
                # Сложные отзывы сразу помечаем обработанными,
                # чтобы не показывать их снова — они уже в чате
                st.mark_processed(uuid)

    if new:
        logger.info("Найдено новых отзывов: %d", new)
    else:
        logger.info("Новых отзывов нет")


# ──────────────── Команда /poll ────────────────

from aiogram.filters import Command
from aiogram.types import Message
from bot.telegram_handler import dp as _dp


@_dp.message(Command("poll"))
async def cmd_poll(message: Message):
    """Ручной запуск проверки отзывов."""
    await message.reply("🔄 Проверяю отзывы...")
    await poll_reviews()
    await message.reply("✅ Готово!")


# ──────────────── Запуск ────────────────

async def main():
    # Устанавливаем начальный режим из .env (только если state.json ещё не существует)
    from pathlib import Path
    if not Path("state.json").exists():
        st.set_mode(MODE)

    logger.info(
        "Бот запущен | режим: %s | интервал: %d мин | LLM: %s",
        st.get_mode(),
        POLL_INTERVAL_MINUTES,
        llm.provider if llm else "отключён",
    )

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(poll_reviews, "interval", minutes=POLL_INTERVAL_MINUTES, id="poll")
    scheduler.start()

    # Первый опрос сразу при старте
    asyncio.create_task(poll_reviews())

    # Подключаем роутер управления шаблонами
    dp.include_router(template_router)

    # Telegram
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
