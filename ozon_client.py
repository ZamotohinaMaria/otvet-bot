import logging
import requests
from config import OZON_CLIENT_ID, OZON_API_KEY, DRY_RUN

BASE_URL = "https://api-seller.ozon.ru"
logger = logging.getLogger(__name__)


class OzonClient:
    def __init__(self):
        self.headers = {
            "Client-Id": OZON_CLIENT_ID,
            "Api-Key": OZON_API_KEY,
            "Content-Type": "application/json",
        }

    def get_unanswered_reviews(self, limit: int = 100) -> list[dict]:
        """Возвращает список неотвеченных отзывов."""
        url = f"{BASE_URL}/v1/review/list"
        payload = {
            "limit": limit,
            "sort_by": "REVIEW_SORT_BY_CREATE_AT",
            "sort_dir": "DESC",
            "filter": {"is_answered": False},
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # API может вернуть данные в result.items или result.reviews
            result = data.get("result", data)
            return result.get("items", result.get("reviews", []))
        except requests.RequestException as e:
            logger.error("Ошибка при получении отзывов: %s", e)
            return []

    def send_reply(self, review_uuid: str, text: str) -> bool:
        """Отправляет ответ на отзыв. В режиме DRY_RUN только логирует."""
        if DRY_RUN:
            logger.info("[DRY_RUN] Ответ на %s: %s", review_uuid, text)
            return True

        url = f"{BASE_URL}/v1/review/comment/create"
        payload = {"review_uuid": review_uuid, "text": text}
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=15)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Ошибка при отправке ответа на %s: %s", review_uuid, e)
            return False

    @staticmethod
    def extract_uuid(review: dict) -> str | None:
        """Извлекает UUID отзыва из разных возможных полей ответа API."""
        return review.get("uuid") or review.get("review_uuid") or review.get("id")
