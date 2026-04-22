"""
Персистентное хранилище состояния бота (state.json).
Хранит: текущий режим, обработанные UUID, отзывы ожидающие подтверждения.
"""
import json
import logging
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"
logger = logging.getLogger(__name__)

_DEFAULT: dict = {
    "mode": "semi",           # "semi" | "auto"
    "processed_uuids": [],    # список обработанных UUID (максимум 5000)
    "pending": {},            # str(telegram_message_id) -> review_data
}


def _load() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("state.json повреждён, создаём заново")
    return dict(_DEFAULT)


def _save(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ──────────────── Режим ────────────────

def get_mode() -> str:
    return _load()["mode"]


def set_mode(mode: str):
    state = _load()
    state["mode"] = mode
    _save(state)


# ──────────────── Обработанные UUID ────────────────

def is_processed(uuid: str) -> bool:
    return uuid in _load()["processed_uuids"]


def mark_processed(uuid: str):
    state = _load()
    if uuid not in state["processed_uuids"]:
        state["processed_uuids"].append(uuid)
        # Не даём расти бесконечно
        state["processed_uuids"] = state["processed_uuids"][-5000:]
    _save(state)


# ──────────────── Pending (ожидают подтверждения) ────────────────

def is_pending(uuid: str) -> bool:
    """Проверяет, отправлен ли уже отзыв в Telegram и ждёт действия."""
    for review_data in _load()["pending"].values():
        if review_data.get("uuid") == uuid:
            return True
    return False


def add_pending(message_id: int, review_data: dict):
    state = _load()
    state["pending"][str(message_id)] = review_data
    _save(state)


def get_pending(message_id: int) -> dict | None:
    """Возвращает данные отзыва по telegram message_id."""
    return _load()["pending"].get(str(message_id))


def find_pending_by_uuid(uuid: str) -> tuple[int, dict] | None:
    """Находит pending запись по UUID отзыва. Возвращает (message_id, data) или None."""
    for msg_id_str, review_data in _load()["pending"].items():
        if review_data.get("uuid") == uuid:
            return int(msg_id_str), review_data
    return None


def remove_pending(message_id: int):
    state = _load()
    state["pending"].pop(str(message_id), None)
    _save(state)


# ──────────────── Статистика ────────────────

def get_stats() -> dict:
    state = _load()
    return {
        "mode": state["mode"],
        "processed": len(state["processed_uuids"]),
        "pending": len(state["pending"]),
    }
