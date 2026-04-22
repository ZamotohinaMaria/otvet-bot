import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

BASE_URL = "https://api-seller.ozon.ru"
REVIEWS_LIST_ENDPOINT = "/v1/review/list"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "reviews.csv"
MIN_LIMIT = 20
MAX_LIMIT = 100


class OzonSubscriptionError(RuntimeError):
    """Метод недоступен на текущей подписке Ozon."""


@dataclass
class ReviewRow:
    created_at: str
    article: str
    rating: str
    review_text: str
    pros: str
    cons: str
    seller_reply: str
    is_answered: str
    review_uuid: str
    product_name: str
    sku: str
    product_id: str


class OzonReviewsParser:
    def __init__(self, client_id: str, api_key: str, timeout: int = 30) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Client-Id": client_id,
                "Api-Key": api_key,
                "Content-Type": "application/json",
            }
        )
        self.timeout = timeout

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{BASE_URL}{endpoint}", json=payload, timeout=self.timeout
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            tail = (response.text or "").strip()[:500]
            if response.status_code == 403 and "subscription" in tail.lower():
                raise OzonSubscriptionError(
                    "Ozon API вернул 403: метод отзывов недоступен для текущей подписки.\n"
                    "Что проверить в кабинете Ozon:\n"
                    "1) Подписка/тариф с доступом к API отзывов.\n"
                    "2) Права API-ключа (доступ к отзывам).\n"
                    "3) Что ключ выпущен для нужного кабинета продавца.\n"
                    f"Детали API: endpoint={endpoint} | response={tail}"
                ) from exc
            raise requests.HTTPError(
                f"{exc} | endpoint={endpoint} | response={tail}",
                response=response,
            ) from exc
        return response.json()

    @staticmethod
    def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
        result = data.get("result", data)
        if isinstance(result, dict):
            items = result.get("items") or result.get("reviews") or []
            return items if isinstance(items, list) else []
        if isinstance(result, list):
            return result
        return []

    @staticmethod
    def _extract_cursor(data: dict[str, Any]) -> str:
        result = data.get("result", data)
        if not isinstance(result, dict):
            return ""

        cursor = (
            result.get("last_id")
            or result.get("next_last_id")
            or result.get("next_page_token")
            or result.get("cursor")
        )
        return str(cursor).strip() if cursor is not None else ""

    def list_reviews(
        self,
        limit: int = 100,
        max_pages: int = 200,
        is_answered: bool | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(MIN_LIMIT, min(MAX_LIMIT, int(limit)))
        all_items: list[dict[str, Any]] = []
        last_id = ""
        seen_ids: set[str] = set()

        for _ in range(max_pages):
            payload: dict[str, Any] = {
                "limit": limit,
                "sort_by": "REVIEW_SORT_BY_CREATE_AT",
                "sort_dir": "DESC",
                "filter": {},
            }
            if last_id:
                payload["last_id"] = last_id
            if is_answered is not None:
                payload["filter"]["is_answered"] = is_answered

            data = self._post(REVIEWS_LIST_ENDPOINT, payload)
            items = self._extract_items(data)
            if not items:
                break

            all_items.extend(items)

            next_last_id = self._extract_cursor(data)
            if not next_last_id or next_last_id in seen_ids:
                break

            seen_ids.add(next_last_id)
            last_id = next_last_id

        return all_items


def _clean_env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не найдена переменная {name} в окружении/.env")

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()

    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"{name} содержит недопустимые символы (например кириллицу). "
            "Проверьте значение в .env и вставьте ключ/ID в оригинальном виде."
        ) from exc

    return value


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _get_path(obj: dict[str, Any], *keys: str) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _extract_reply(review: dict[str, Any]) -> str:
    direct = (
        _get_path(review, "answer", "text")
        or _get_path(review, "seller_comment", "text")
        or review.get("comment")
    )
    if direct:
        return _to_str(direct)

    comments = review.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, dict):
                text = comment.get("text")
                if text:
                    return _to_str(text)

    return ""


def build_rows(reviews: list[dict[str, Any]]) -> list[ReviewRow]:
    rows: list[ReviewRow] = []

    for review in reviews:
        product = review.get("product") if isinstance(review.get("product"), dict) else {}

        article = (
            review.get("offer_id")
            or product.get("offer_id")
            or review.get("article")
            or ""
        )
        rating = review.get("rating") or review.get("score") or ""
        review_text = (
            review.get("text")
            or review.get("content")
            or review.get("comment")
            or ""
        )
        pros = review.get("pros") or review.get("positive_text") or ""
        cons = review.get("cons") or review.get("negative_text") or ""
        seller_reply = _extract_reply(review)

        is_answered = review.get("is_answered")
        if is_answered is None:
            is_answered = bool(seller_reply)

        created_at = (
            review.get("created_at")
            or review.get("createdAt")
            or review.get("published_at")
            or review.get("create_time")
            or ""
        )

        review_uuid = review.get("uuid") or review.get("review_uuid") or review.get("id") or ""
        product_name = review.get("product_name") or product.get("name") or ""
        sku = review.get("sku") or product.get("sku") or ""
        product_id = review.get("product_id") or product.get("id") or ""

        rows.append(
            ReviewRow(
                created_at=_to_str(created_at),
                article=_to_str(article),
                rating=_to_str(rating),
                review_text=_to_str(review_text),
                pros=_to_str(pros),
                cons=_to_str(cons),
                seller_reply=_to_str(seller_reply),
                is_answered=_to_str(is_answered),
                review_uuid=_to_str(review_uuid),
                product_name=_to_str(product_name),
                sku=_to_str(sku),
                product_id=_to_str(product_id),
            )
        )

    return rows


def save_csv(rows: list[ReviewRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "дата",
                "артикул",
                "рейтинг",
                "текст отзыва",
                "достоинства",
                "недостатки",
                "ответ продавца",
                "отвечен",
                "uuid отзыва",
                "название товара",
                "sku",
                "id товара",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.created_at,
                    row.article,
                    row.rating,
                    row.review_text,
                    row.pros,
                    row.cons,
                    row.seller_reply,
                    row.is_answered,
                    row.review_uuid,
                    row.product_name,
                    row.sku,
                    row.product_id,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Парсер отзывов Ozon в CSV. "
            "Учитывает пагинацию и разные форматы ответа API."
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument(
        "--only-unanswered",
        action="store_true",
        help="Выгрузить только неотвеченные отзывы.",
    )
    parser.add_argument(
        "--only-answered",
        action="store_true",
        help="Выгрузить только отвеченные отзывы.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()

    client_id = _clean_env_value("OZON_CLIENT_ID")
    api_key = _clean_env_value("OZON_API_KEY")

    args = parse_args()
    normalized_limit = max(MIN_LIMIT, min(MAX_LIMIT, int(args.limit)))
    if normalized_limit != args.limit:
        print(
            f"Предупреждение: --limit={args.limit} вне диапазона [{MIN_LIMIT}, {MAX_LIMIT}], "
            f"использую {normalized_limit}."
        )

    if args.only_unanswered and args.only_answered:
        raise RuntimeError("Нельзя одновременно указывать --only-unanswered и --only-answered")

    is_answered: bool | None = None
    if args.only_unanswered:
        is_answered = False
    elif args.only_answered:
        is_answered = True

    parser = OzonReviewsParser(client_id=client_id, api_key=api_key)
    try:
        reviews = parser.list_reviews(
            limit=normalized_limit,
            max_pages=args.max_pages,
            is_answered=is_answered,
        )
    except OzonSubscriptionError as exc:
        print(str(exc))
        sys.exit(2)

    rows = build_rows(reviews)
    save_csv(rows, args.output)

    print(f"Готово. Записано строк: {len(rows)}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
