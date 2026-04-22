"""
Управление шаблонами ответов через Telegram.
Добавление, редактирование (ответы / ключевые слова / звёзды / описание), удаление.
"""
import json
import logging
import re
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import bot.classifier as classifier

logger = logging.getLogger(__name__)
router = Router()

TEMPLATES_PATH = Path(__file__).parent / "templates.json"

# ──────────────── I/O ────────────────

def _load() -> dict:
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(templates: dict):
    with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)
    classifier.reload()


# ──────────────── FSM ────────────────

class AddTemplate(StatesGroup):
    key         = State()
    description = State()
    stars       = State()
    keywords    = State()
    responses   = State()   # сбор ответов по одному


class EditTemplate(StatesGroup):
    value = State()         # универсальное состояние для ввода нового значения


# ──────────────── Клавиатуры ────────────────

def _kb_list() -> InlineKeyboardMarkup:
    templates = _load()
    rows = [
        [InlineKeyboardButton(text=f"📌 {key}", callback_data=f"tmpl:view:{key}")]
        for key in templates
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="tmpl:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_view(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"tmpl:edit:{key}"),
            InlineKeyboardButton(text="🗑️ Удалить",       callback_data=f"tmpl:del:{key}"),
        ],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="tmpl:list")],
    ])


def _kb_edit(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответы",           callback_data=f"tmpl:resp:list:{key}")],
        [InlineKeyboardButton(text="🔑 Ключевые слова",   callback_data=f"tmpl:ef:{key}:keywords")],
        [InlineKeyboardButton(text="⭐ Диапазон звёзд",   callback_data=f"tmpl:ef:{key}:stars")],
        [InlineKeyboardButton(text="📄 Описание",         callback_data=f"tmpl:ef:{key}:description")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data=f"tmpl:view:{key}")],
    ])


def _kb_responses(key: str, responses: list) -> InlineKeyboardMarkup:
    rows = []
    for i in range(len(responses)):
        rows.append([
            InlineKeyboardButton(text=f"✏️ №{i+1}", callback_data=f"tmpl:re:{key}:{i}"),
            InlineKeyboardButton(text=f"🗑️ №{i+1}", callback_data=f"tmpl:rd:{key}:{i}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить ответ", callback_data=f"tmpl:ra:{key}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад",          callback_data=f"tmpl:edit:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_add_more() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Ещё ответ",    callback_data="add:more"),
        InlineKeyboardButton(text="✅ Сохранить",    callback_data="add:done"),
    ]])


# ──────────────── Форматирование ────────────────

def _fmt_template(key: str, tpl: dict) -> str:
    stars = f"⭐ {tpl.get('min_stars', 1)}–{tpl.get('max_stars', 5)}"
    kws   = tpl.get("keywords", [])
    resps = tpl.get("responses", [])

    lines = [
        f"📌 *{key}*",
        f"_{tpl.get('description', '')}_",
        f"{stars}  |  ключевых слов: {len(kws)}  |  ответов: {len(resps)}",
        "",
    ]
    if kws:
        lines.append("*Ключевые слова:*")
        lines.append(", ".join(f"`{k}`" for k in kws))
        lines.append("")
    lines.append("*Ответы:*")
    for i, r in enumerate(resps, 1):
        lines.append(f"{i}. {r}")
    return "\n".join(lines)


def _fmt_responses(key: str, responses: list) -> str:
    lines = [f"💬 *Ответы шаблона `{key}`*\n"]
    for i, r in enumerate(responses, 1):
        lines.append(f"*{i}.* {r}")
    return "\n".join(lines)


# ──────────────── /templates ────────────────

@router.message(Command("templates"))
async def cmd_templates(message: Message):
    templates = _load()
    await message.answer(
        f"📋 *Шаблоны ответов* — всего {len(templates)}\n\nВыбери для просмотра или редактирования:",
        parse_mode="Markdown",
        reply_markup=_kb_list(),
    )


@router.callback_query(F.data == "tmpl:list")
async def cb_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    templates = _load()
    await callback.message.edit_text(
        f"📋 *Шаблоны ответов* — всего {len(templates)}\n\nВыбери для просмотра или редактирования:",
        parse_mode="Markdown",
        reply_markup=_kb_list(),
    )
    await callback.answer()


# ──────────────── Просмотр ────────────────

@router.callback_query(F.data.startswith("tmpl:view:"))
async def cb_view(callback: CallbackQuery):
    key = callback.data[len("tmpl:view:"):]
    templates = _load()
    if key not in templates:
        await callback.answer("Шаблон не найден")
        return
    await callback.message.edit_text(
        _fmt_template(key, templates[key]),
        parse_mode="Markdown",
        reply_markup=_kb_view(key),
    )
    await callback.answer()


# ──────────────── Удаление ────────────────

@router.callback_query(F.data.startswith("tmpl:del:"))
async def cb_del_confirm(callback: CallbackQuery):
    key = callback.data[len("tmpl:del:"):]
    await callback.message.edit_text(
        f"⚠️ Удалить шаблон *{key}*?\nДействие необратимо.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tmpl:dok:{key}"),
            InlineKeyboardButton(text="❌ Отмена",      callback_data=f"tmpl:view:{key}"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tmpl:dok:"))
async def cb_del_ok(callback: CallbackQuery):
    key = callback.data[len("tmpl:dok:"):]
    templates = _load()
    if key in templates:
        del templates[key]
        _save(templates)
        await callback.answer(f"Шаблон «{key}» удалён")
    else:
        await callback.answer("Шаблон не найден")
    templates = _load()
    await callback.message.edit_text(
        f"📋 *Шаблоны ответов* — всего {len(templates)}",
        parse_mode="Markdown",
        reply_markup=_kb_list(),
    )


# ──────────────── Меню редактирования ────────────────

@router.callback_query(F.data.startswith("tmpl:edit:"))
async def cb_edit_menu(callback: CallbackQuery):
    key = callback.data[len("tmpl:edit:"):]
    await callback.message.edit_text(
        f"✏️ *Редактирование шаблона `{key}`*\n\nЧто изменить?",
        parse_mode="Markdown",
        reply_markup=_kb_edit(key),
    )
    await callback.answer()


# ──────────────── Редактирование поля (описание / ключевые слова / звёзды) ────────────────

@router.callback_query(F.data.startswith("tmpl:ef:"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext):
    # tmpl:ef:<key>:<field>
    parts = callback.data.split(":")   # ["tmpl","ef",key,field]
    key, field = parts[2], parts[3]
    tpl = _load().get(key, {})

    current = {
        "description": tpl.get("description", ""),
        "keywords":    ", ".join(tpl.get("keywords", [])) or "нет",
        "stars":       f"{tpl.get('min_stars',1)}-{tpl.get('max_stars',5)}",
    }[field]

    prompts = {
        "description": "📄 Введите новое описание:",
        "keywords":    "🔑 Ключевые слова через запятую (или `нет` чтобы очистить):",
        "stars":       "⭐ Диапазон звёзд формата `мин-макс`, например `4-5`:",
    }

    await state.update_data(edit_key=key, edit_field=field)
    await state.set_state(EditTemplate.value)
    await callback.answer()
    await callback.message.reply(
        f"{prompts[field]}\n\n_Сейчас:_ `{current}`\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(EditTemplate.value)
async def handle_edit_value(message: Message, state: FSMContext):
    data  = await state.get_data()
    key   = data["edit_key"]
    field = data["edit_field"]
    value = message.text.strip()

    templates = _load()
    if key not in templates:
        await message.reply("Шаблон не найден.")
        await state.clear()
        return

    if field == "description":
        templates[key]["description"] = value

    elif field == "keywords":
        templates[key]["keywords"] = (
            [] if value.lower() == "нет"
            else [k.strip() for k in value.split(",") if k.strip()]
        )

    elif field == "stars":
        m = re.fullmatch(r"(\d)-(\d)", value.strip())
        if not m or not (1 <= int(m[1]) <= int(m[2]) <= 5):
            await message.reply("❌ Формат: `1-5`, `4-5` и т.д. Попробуй ещё раз.", parse_mode="Markdown")
            return
        templates[key]["min_stars"] = int(m[1])
        templates[key]["max_stars"] = int(m[2])

    elif field == "response":
        idx = data["resp_index"]
        templates[key]["responses"][idx] = value

    elif field == "response_add":
        templates[key].setdefault("responses", []).append(value)

    _save(templates)
    await state.clear()
    field_label = {"description": "описание", "keywords": "ключевые слова",
                   "stars": "диапазон звёзд", "response": "ответ",
                   "response_add": "ответ"}.get(field, field)
    await message.reply(f"✅ Поле *{field_label}* обновлено в шаблоне *{key}*", parse_mode="Markdown")


# ──────────────── Управление ответами ────────────────

@router.callback_query(F.data.startswith("tmpl:resp:list:"))
async def cb_resp_list(callback: CallbackQuery):
    key = callback.data[len("tmpl:resp:list:"):]
    tpl = _load().get(key, {})
    responses = tpl.get("responses", [])
    await callback.message.edit_text(
        _fmt_responses(key, responses),
        parse_mode="Markdown",
        reply_markup=_kb_responses(key, responses),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tmpl:rd:"))   # response delete
async def cb_resp_del(callback: CallbackQuery):
    parts = callback.data.split(":")   # tmpl:rd:<key>:<idx>
    key, idx = parts[2], int(parts[3])
    templates = _load()
    responses = templates[key].get("responses", [])

    if len(responses) <= 1:
        await callback.answer("❌ Нельзя удалить последний ответ")
        return

    responses.pop(idx)
    _save(templates)
    await callback.answer(f"Ответ №{idx+1} удалён")
    await callback.message.edit_text(
        _fmt_responses(key, responses),
        parse_mode="Markdown",
        reply_markup=_kb_responses(key, responses),
    )


@router.callback_query(F.data.startswith("tmpl:re:"))   # response edit
async def cb_resp_edit(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")   # tmpl:re:<key>:<idx>
    key, idx = parts[2], int(parts[3])
    current = _load()[key]["responses"][idx]

    await state.update_data(edit_key=key, edit_field="response", resp_index=idx)
    await state.set_state(EditTemplate.value)
    await callback.answer()
    await callback.message.reply(
        f"✏️ Введите новый текст для ответа №{idx+1}:\n\n_Сейчас:_ {current}\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("tmpl:ra:"))   # response add
async def cb_resp_add(callback: CallbackQuery, state: FSMContext):
    key = callback.data[len("tmpl:ra:"):]
    await state.update_data(edit_key=key, edit_field="response_add")
    await state.set_state(EditTemplate.value)
    await callback.answer()
    await callback.message.reply(
        f"➕ Введите текст нового ответа для шаблона *{key}*:\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


# ──────────────── Добавление нового шаблона (FSM) ────────────────

@router.callback_query(F.data == "tmpl:add")
async def cb_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTemplate.key)
    await callback.answer()
    await callback.message.reply(
        "➕ *Новый шаблон* — шаг 1/5\n\n"
        "Введите *ключ* шаблона — короткое латинское название без пробелов.\n"
        "Например: `positive_phone`, `delivery_slow`\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(AddTemplate.key)
async def add_key(message: Message, state: FSMContext):
    key = message.text.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", key):
        await message.reply(
            "❌ Ключ должен начинаться с буквы, содержать только латиницу/цифры/_, длина 2-40.\nПопробуй ещё раз:"
        )
        return
    if key in _load():
        await message.reply(f"❌ Шаблон `{key}` уже существует. Введи другое имя:", parse_mode="Markdown")
        return
    await state.update_data(key=key)
    await state.set_state(AddTemplate.description)
    await message.reply(
        f"✅ Ключ: `{key}`\n\n*Шаг 2/5* — Введите описание (для кого/чего этот шаблон):\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(AddTemplate.description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddTemplate.stars)
    await message.reply(
        "✅ Описание сохранено.\n\n"
        "*Шаг 3/5* — Введите диапазон звёзд формата `мин-макс`:\n"
        "Например: `4-5` (только хорошие), `1-5` (любые)\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(AddTemplate.stars)
async def add_stars(message: Message, state: FSMContext):
    m = re.fullmatch(r"(\d)-(\d)", message.text.strip())
    if not m or not (1 <= int(m[1]) <= int(m[2]) <= 5):
        await message.reply("❌ Формат: `1-5`, `3-5`, `4-5` и т.д. Попробуй ещё раз:", parse_mode="Markdown")
        return
    await state.update_data(min_stars=int(m[1]), max_stars=int(m[2]))
    await state.set_state(AddTemplate.keywords)
    await message.reply(
        "✅ Звёзды сохранены.\n\n"
        "*Шаг 4/5* — Введите ключевые слова через запятую\n"
        "(или `нет` — шаблон будет применяться без ключевых слов, как запасной):\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(AddTemplate.keywords)
async def add_keywords(message: Message, state: FSMContext):
    raw = message.text.strip()
    keywords = [] if raw.lower() == "нет" else [k.strip() for k in raw.split(",") if k.strip()]
    await state.update_data(keywords=keywords)
    await state.set_state(AddTemplate.responses)
    await message.reply(
        "✅ Ключевые слова сохранены.\n\n"
        "*Шаг 5/5* — Введите первый вариант ответа:\n\n/cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(AddTemplate.responses)
async def add_response(message: Message, state: FSMContext):
    data = await state.get_data()
    responses = data.get("responses", [])
    responses.append(message.text.strip())
    await state.update_data(responses=responses)
    await message.reply(
        f"✅ Ответ №{len(responses)} добавлен.\n\nДобавить ещё вариант ответа или сохранить шаблон?",
        reply_markup=_kb_add_more(),
    )


@router.callback_query(F.data == "add:more", AddTemplate.responses)
async def add_more(callback: CallbackQuery):
    await callback.answer()
    await callback.message.reply("Введите следующий вариант ответа:")


@router.callback_query(F.data == "add:done", AddTemplate.responses)
async def add_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    key = data["key"]
    new_tpl = {
        "description": data["description"],
        "keywords":    data["keywords"],
        "min_stars":   data["min_stars"],
        "max_stars":   data["max_stars"],
        "responses":   data["responses"],
    }
    templates = _load()
    templates[key] = new_tpl
    _save(templates)
    await state.clear()
    await callback.answer("Шаблон сохранён!")
    await callback.message.reply(
        f"✅ Шаблон *{key}* создан с {len(new_tpl['responses'])} вариантами ответа!\n\n"
        f"Посмотреть: /templates",
        parse_mode="Markdown",
    )
