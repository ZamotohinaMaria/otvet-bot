"""
Telegram-бот: обработчики команд и callback-кнопок.
Экспортирует bot, dp и send_review_to_chat для использования в bot.py.
"""
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import state as st
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from ozon_client import OzonClient

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
ozon = OzonClient()


# ──────────────── FSM состояния ────────────────

class EditReview(StatesGroup):
    waiting_for_text = State()


# ──────────────── Вспомогательные функции ────────────────

def _stars(n: int) -> str:
    return "⭐" * max(0, min(5, n))


def _build_keyboard(review_uuid: str, has_template: bool) -> InlineKeyboardMarkup:
    """Клавиатура для отзыва в semi-режиме или для сложного отзыва."""
    rows = []
    if has_template:
        rows.append([
            InlineKeyboardButton(text="✅ Отправить", callback_data=f"approve:{review_uuid}"),
            InlineKeyboardButton(text="✏️ Изменить",  callback_data=f"edit:{review_uuid}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="✏️ Написать ответ", callback_data=f"edit:{review_uuid}"),
        ])
    rows.append([
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"skip:{review_uuid}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_message(review: dict, proposed: str | None, mode: str, is_auto_notify: bool = False) -> str:
    stars = _stars(review.get("rating", 0))
    author = review.get("author_name") or "Анонимно"
    text = review.get("text") or "(без текста)"

    lines = [f"📩 *Новый отзыв*", f"{stars} — {author}", "", f"_{text}_"]

    if is_auto_notify:
        lines += ["", f"✅ *Ответ отправлен автоматически:*", f"_{proposed}_"]
    elif proposed:
        lines += ["", f"💬 *Предлагаю ответить:*", f"_{proposed}_"]
    else:
        lines += ["", "⚠️ *Сложный отзыв — нужен ручной ответ*"]

    return "\n".join(lines)


# ──────────────── Главная функция отправки отзыва в чат ────────────────

async def send_review_to_chat(review: dict, template_key: str | None, proposed: str | None):
    """
    Отправляет отзыв в Telegram-чат.
    - auto + шаблон найден  → уведомление (ответ уже отправлен)
    - semi + шаблон найден  → кнопки "Отправить / Изменить / Пропустить"
    - любой режим + сложный → кнопки "Написать ответ / Пропустить"
    """
    mode = st.get_mode()
    uuid = review.get("uuid") or review.get("review_uuid") or ""

    if mode == "auto" and proposed:
        # Просто уведомление — ответ уже ушёл на Ozon
        text = _format_message(review, proposed, mode, is_auto_notify=True)
        await bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")
        return

    # Semi-режим или сложный отзыв — нужна кнопочная клавиатура
    text = _format_message(review, proposed, mode)
    keyboard = _build_keyboard(uuid, has_template=bool(proposed))
    msg = await bot.send_message(
        TELEGRAM_CHAT_ID, text, parse_mode="Markdown", reply_markup=keyboard
    )

    review_data = {
        "uuid": uuid,
        "template_key": template_key,
        "proposed_response": proposed,
        "author": review.get("author_name", ""),
        "rating": review.get("rating", 0),
    }
    st.add_pending(msg.message_id, review_data)


# ──────────────── Callback: ✅ Одобрить ────────────────

@dp.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery):
    uuid = callback.data.split(":", 1)[1]
    result = st.find_pending_by_uuid(uuid)

    if not result:
        await callback.answer("Уже обработан")
        return

    msg_id, review_data = result
    proposed = review_data.get("proposed_response", "")

    success = ozon.send_reply(uuid, proposed)
    if success:
        st.mark_processed(uuid)
        st.remove_pending(msg_id)
        new_text = callback.message.text + f"\n\n✅ *Отправлено:* _{proposed}_"
        await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
        await callback.answer("Ответ отправлен!")
    else:
        await callback.answer("❌ Ошибка при отправке. Попробуйте снова.")


# ──────────────── Callback: ✏️ Изменить / Написать ────────────────

@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit(callback: CallbackQuery, state: FSMContext):
    uuid = callback.data.split(":", 1)[1]
    await state.update_data(uuid=uuid, original_message_id=callback.message.message_id)
    await state.set_state(EditReview.waiting_for_text)
    await callback.answer()
    await callback.message.reply("✏️ Введите текст ответа (или /cancel для отмены):")


@dp.message(EditReview.waiting_for_text)
async def handle_custom_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    uuid = data["uuid"]
    original_msg_id = data["original_message_id"]

    success = ozon.send_reply(uuid, message.text)
    if success:
        st.mark_processed(uuid)
        st.remove_pending(original_msg_id)
        await state.clear()
        await message.reply(f"✅ Ответ отправлен: _{message.text}_", parse_mode="Markdown")
        # Убираем кнопки с исходного сообщения
        try:
            await bot.edit_message_reply_markup(
                chat_id=TELEGRAM_CHAT_ID, message_id=original_msg_id, reply_markup=None
            )
        except Exception:
            pass
    else:
        await message.reply("❌ Ошибка при отправке. Попробуйте ещё раз.")


# ──────────────── Callback: ⏭️ Пропустить ────────────────

@dp.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery):
    uuid = callback.data.split(":", 1)[1]
    result = st.find_pending_by_uuid(uuid)

    if not result:
        await callback.answer("Уже обработан")
        return

    msg_id, _ = result
    st.mark_processed(uuid)
    st.remove_pending(msg_id)
    new_text = callback.message.text + "\n\n⏭️ _Пропущено_"
    await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)
    await callback.answer("Пропущено")


# ──────────────── Команды ────────────────

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    stats = st.get_stats()
    mode = stats["mode"]
    mode_label = "🤖 Авто" if mode == "auto" else "👤 Полуавто"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Шаблоны",             callback_data="menu:templates")],
        [
            InlineKeyboardButton(text=f"⚙️ Режим: {mode_label}", callback_data="menu:mode"),
            InlineKeyboardButton(text="📊 Статистика",           callback_data="menu:stats"),
        ],
        [InlineKeyboardButton(text="🔄 Проверить отзывы",    callback_data="menu:poll")],
    ])


@dp.message(Command("start", "help", "menu"))
async def cmd_menu(message: Message):
    await message.reply(
        "🤖 *Бот ответов на отзывы Ozon*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )


@dp.callback_query(F.data == "menu:templates")
async def cb_menu_templates(callback: CallbackQuery):
    """Перенаправляет в менеджер шаблонов (обрабатывается в template_manager.py)."""
    from template_manager import _kb_list, _load as tmpl_load
    templates = tmpl_load()
    await callback.message.edit_text(
        f"📋 *Шаблоны ответов* — всего {len(templates)}\n\nВыбери для просмотра или редактирования:",
        parse_mode="Markdown",
        reply_markup=_kb_list(),
    )
    await callback.answer()


@dp.callback_query(F.data == "menu:mode")
async def cb_menu_mode(callback: CallbackQuery):
    current = st.get_mode()
    await callback.message.edit_text(
        f"⚙️ *Режим работы*\n\nТекущий: *{'🤖 авто' if current == 'auto' else '👤 полуавто'}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Авто",     callback_data="menu:setmode:auto"),
                InlineKeyboardButton(text="👤 Полуавто", callback_data="menu:setmode:semi"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("menu:setmode:"))
async def cb_menu_setmode(callback: CallbackQuery):
    new_mode = callback.data.split(":")[-1]
    st.set_mode(new_mode)
    emoji = "🤖" if new_mode == "auto" else "👤"
    await callback.answer(f"{emoji} Режим переключён на {new_mode}")
    await callback.message.edit_text(
        "🤖 *Бот ответов на отзывы Ozon*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )


@dp.callback_query(F.data == "menu:stats")
async def cb_menu_stats(callback: CallbackQuery):
    stats = st.get_stats()
    emoji = "🤖" if stats["mode"] == "auto" else "👤"
    await callback.message.edit_text(
        f"📊 *Статистика*\n\n"
        f"Режим: {emoji} {stats['mode']}\n"
        f"Обработано отзывов: {stats['processed']}\n"
        f"Ожидают подтверждения: {stats['pending']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")]
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data == "menu:poll")
async def cb_menu_poll(callback: CallbackQuery):
    await callback.answer("🔄 Запускаю проверку...")
    await callback.message.edit_text(
        "🔄 Проверяю новые отзывы...",
        parse_mode="Markdown",
    )
    # Импорт здесь чтобы избежать циклической зависимости
    from bot import poll_reviews
    await poll_reviews()
    await callback.message.edit_text(
        "✅ Проверка завершена!\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )


@dp.callback_query(F.data == "menu:back")
async def cb_menu_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 *Бот ответов на отзывы Ozon*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )
    await callback.answer()


@dp.message(Command("mode"))
async def cmd_mode(message: Message):
    args = message.text.strip().split()
    current = st.get_mode()

    if len(args) < 2:
        await message.reply(
            "🤖 *Бот ответов на отзывы Ozon*\n\nВыбери действие:",
            parse_mode="Markdown",
            reply_markup=_main_menu_keyboard(),
        )
        return

    new_mode = args[1].lower()
    if new_mode not in ("auto", "semi"):
        await message.reply("Допустимые значения: `auto` или `semi`", parse_mode="Markdown")
        return

    st.set_mode(new_mode)
    emoji = "🤖" if new_mode == "auto" else "👤"
    await message.reply(f"{emoji} Режим переключён на *{new_mode}*", parse_mode="Markdown")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = st.get_stats()
    emoji = "🤖" if stats["mode"] == "auto" else "👤"
    await message.reply(
        f"📊 *Статистика*\n\n"
        f"Режим: {emoji} {stats['mode']}\n"
        f"Обработано отзывов: {stats['processed']}\n"
        f"Ожидают подтверждения: {stats['pending']}",
        parse_mode="Markdown",
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.reply("Отменено.")
    else:
        await message.reply("Нечего отменять.")
