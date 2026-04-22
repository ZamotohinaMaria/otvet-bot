import json
import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = Path(__file__).parent / "templates.json"
with open(_TEMPLATES_PATH, "r", encoding="utf-8") as _f:
    TEMPLATES: dict = json.load(_f)


def reload():
    """Перечитывает templates.json — вызывать после любого изменения шаблонов."""
    global TEMPLATES
    with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
        TEMPLATES = json.load(f)

# Слова-сигналы сложного отзыва
_COMPLEX_KEYWORDS = [
    "возврат", "вернуть", "возврата", "возвращу",
    "брак", "бракованный", "бракованная",
    "сломан", "сломана", "сломано", "не работает", "не работают",
    "обман", "обманули", "мошенник", "мошенники",
    "претензия", "жалоба",
    "не соответствует", "не то", "пришло не то", "не тот товар",
    "испорчен", "испорчена", "испорчено",
    "повреждён", "повреждена", "повреждено",
    "деньги назад", "верните деньги",
    "некачественный", "некачественная",
    "ужасно", "отвратительно", "кошмар",
]


def _complexity_score(review: dict) -> int:
    """Считает очки сложности. Порог >= 2 — отзыв считается сложным."""
    score = 0
    text = (review.get("text") or "").lower()
    stars = review.get("rating", 5)

    if stars <= 2:
        score += 2
    elif stars == 3:
        score += 1

    for kw in _COMPLEX_KEYWORDS:
        if kw in text:
            score += 2
            break

    if "?" in text:
        score += 1

    if len(text) > 400:
        score += 1

    return score


def _rule_match(review: dict) -> str | None:
    """Уровень 1: быстрое сопоставление по ключевым словам и рейтингу."""
    text = (review.get("text") or "").lower()
    stars = review.get("rating", 5)
    text_len = len(text)

    for key, tpl in TEMPLATES.items():
        min_s = tpl.get("min_stars", 1)
        max_s = tpl.get("max_stars", 5)
        max_tl = tpl.get("max_text_length")

        if not (min_s <= stars <= max_s):
            continue

        if max_tl is not None and text_len > max_tl:
            continue

        # Шаблон без ключевых слов — срабатывает последним (нейтральный/базовый)
        kws = tpl.get("keywords", [])
        if not kws:
            continue

        for kw in kws:
            if kw.lower() in text:
                return key

    # Второй проход: шаблоны без ключевых слов (нейтральные/базовые)
    for key, tpl in TEMPLATES.items():
        min_s = tpl.get("min_stars", 1)
        max_s = tpl.get("max_stars", 5)
        max_tl = tpl.get("max_text_length")

        if not (min_s <= stars <= max_s):
            continue
        if max_tl is not None and text_len > max_tl:
            continue
        if tpl.get("keywords"):
            continue

        return key

    return None


def pick_response(template_key: str) -> str:
    """Возвращает случайный ответ из шаблона."""
    return random.choice(TEMPLATES[template_key]["responses"])


def classify_review(review: dict, llm_client=None) -> tuple[str | None, str | None]:
    """
    Классифицирует отзыв.
    Возвращает (template_key, response_text) или (None, None) если отзыв сложный.
    """
    # Сначала проверяем сложность
    if _complexity_score(review) >= 2:
        logger.info("Отзыв %s — сложный (по правилам)", review.get("uuid", "?"))
        return None, None

    # Уровень 1: правила
    key = _rule_match(review)
    if key:
        logger.info("Отзыв %s → шаблон '%s' (по правилам)", review.get("uuid", "?"), key)
        return key, pick_response(key)

    # Уровень 2: LLM (отключён — раскомментируй когда будет API-ключ)
    # if llm_client:
    #     key = llm_client.classify(review.get("text", ""), TEMPLATES)
    #     if key:
    #         logger.info("Отзыв %s → шаблон '%s' (LLM)", review.get("uuid", "?"), key)
    #         return key, pick_response(key)

    # Запасной шаблон — подходит для любого отзыва без явных жалоб
    logger.info("Отзыв %s → шаблон 'fallback_general' (запасной)", review.get("uuid", "?"))
    return "fallback_general", pick_response("fallback_general")
