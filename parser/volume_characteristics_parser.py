import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

BASE_URL = "https://api-seller.ozon.ru"
PRODUCT_LIST_ENDPOINT = "/v3/product/list"
PRODUCT_ATTRIBUTES_ENDPOINT = "/v3/products/info/attributes"
PRODUCT_ATTRIBUTES_V4_ENDPOINT = "/v4/product/info/attributes"
PRODUCT_INFO_LIST_V3_ENDPOINT = "/v3/product/info/list"
PRODUCT_INFO_LIST_V2_ENDPOINT = "/v2/product/info/list"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "volume_characteristics.csv"


@dataclass
class ProductRow:
    article: str
    volume_cm3: float | None
    weight: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None


class OzonVolumeParser:
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
            raise requests.HTTPError(
                f"{exc} | endpoint={endpoint} | response={tail}",
                response=response,
            ) from exc
        return response.json()

    def list_products(self, batch_size: int = 1000) -> dict[int, str]:
        products: dict[int, str] = {}
        last_id = ""

        while True:
            payload = {
                "filter": {"visibility": "ALL"},
                "last_id": last_id,
                "limit": batch_size,
            }
            data = self._post(PRODUCT_LIST_ENDPOINT, payload)
            result = data.get("result", {})
            items = result.get("items", [])

            for item in items:
                product_id = item.get("product_id")
                article = item.get("offer_id")
                if isinstance(product_id, int) and isinstance(article, str) and article:
                    products[product_id] = article

            last_id = result.get("last_id") or ""
            if not items or not last_id:
                break

        return products

    def _fetch_dimensions_attributes(self, product_ids: list[int]) -> list[dict[str, Any]]:
        payload = {
            "filter": {"product_id": product_ids, "visibility": "ALL"},
            "limit": len(product_ids),
            "sort_dir": "ASC",
        }
        data = self._post(PRODUCT_ATTRIBUTES_ENDPOINT, payload)
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    def _fetch_dimensions_attributes_v4(self, product_ids: list[int]) -> list[dict[str, Any]]:
        payload = {
            "filter": {"product_id": product_ids, "visibility": "ALL"},
            "limit": len(product_ids),
            "sort_dir": "ASC",
        }
        data = self._post(PRODUCT_ATTRIBUTES_V4_ENDPOINT, payload)
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    def _fetch_dimensions_info_v3(self, product_ids: list[int]) -> list[dict[str, Any]]:
        payload = {"product_id": product_ids}
        data = self._post(PRODUCT_INFO_LIST_V3_ENDPOINT, payload)
        result = data.get("result", {})
        if isinstance(result, list):
            return result
        items = result.get("items", []) if isinstance(result, dict) else []
        return items if isinstance(items, list) else []

    def _fetch_dimensions_info_v2(self, product_ids: list[int]) -> list[dict[str, Any]]:
        payload = {"product_id": product_ids}
        data = self._post(PRODUCT_INFO_LIST_V2_ENDPOINT, payload)
        result = data.get("result", {})
        items = result.get("items", []) if isinstance(result, dict) else []
        return items if isinstance(items, list) else []

    def fetch_dimensions(self, product_ids: list[int]) -> list[dict[str, Any]]:
        errors: list[str] = []
        for fetcher in (
            self._fetch_dimensions_attributes,
            self._fetch_dimensions_attributes_v4,
            self._fetch_dimensions_info_v3,
            self._fetch_dimensions_info_v2,
        ):
            try:
                items = fetcher(product_ids)
                if items:
                    return items
            except requests.HTTPError as exc:
                errors.append(str(exc))
                continue

        details = "\n".join(errors) if errors else "Нет данных."
        raise RuntimeError(
            "Не удалось получить габариты ни одним из поддерживаемых методов Ozon API.\n"
            f"{details}"
        )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", ".")
    if not text:
        return None

    num = ""
    dot_seen = False
    for char in text:
        if char.isdigit() or (char == "-" and not num):
            num += char
            continue
        if char == "." and not dot_seen:
            num += char
            dot_seen = True

    if not num or num in {"-", ".", "-."}:
        return None

    try:
        return float(num)
    except ValueError:
        return None


def _extract_from_attributes(attributes: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    for attribute in attributes:
        name = str(attribute.get("name", "")).strip().lower()
        if name and any(key in name for key in keys):
            values = attribute.get("values", [])
            if isinstance(values, list):
                for value_obj in values:
                    if isinstance(value_obj, dict):
                        candidate = (
                            value_obj.get("value")
                            or value_obj.get("name")
                            or value_obj.get("text")
                        )
                        numeric = _to_float(candidate)
                        if numeric is not None:
                            return numeric
    return None


def _extract_dimension(item: dict[str, Any], kind: str) -> float | None:
    key_map = {
        "length": ("length", "depth", "длина", "глубина"),
        "width": ("width", "ширина"),
        "height": ("height", "высота"),
    }

    # Часто размеры приходят в отдельном объекте.
    dimensions = item.get("dimensions")
    if isinstance(dimensions, dict):
        direct = _to_float(dimensions.get(kind))
        if direct is not None:
            return direct

    direct_keys = [kind]
    if kind == "length":
        direct_keys.append("depth")

    for direct_key in direct_keys:
        direct = _to_float(item.get(direct_key))
        if direct is not None:
            return direct

    sources = item.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                for direct_key in direct_keys:
                    from_source = _to_float(source.get(direct_key))
                    if from_source is not None:
                        return from_source

    attributes = item.get("attributes", [])
    if isinstance(attributes, list):
        return _extract_from_attributes(attributes, key_map[kind])

    return None


def _extract_weight(item: dict[str, Any]) -> float | None:
    weight_keys = ("weight", "weight_net", "weight_gross", "вес", "масса")

    dimensions = item.get("dimensions")
    if isinstance(dimensions, dict):
        for key in ("weight", "weight_net", "weight_gross"):
            value = _to_float(dimensions.get(key))
            if value is not None:
                return value

    for key in ("weight", "weight_net", "weight_gross"):
        value = _to_float(item.get(key))
        if value is not None:
            return value

    sources = item.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                for key in ("weight", "weight_net", "weight_gross"):
                    value = _to_float(source.get(key))
                    if value is not None:
                        return value

    attributes = item.get("attributes", [])
    if isinstance(attributes, list):
        return _extract_from_attributes(attributes, weight_keys)

    return None


def build_rows(items: list[dict[str, Any]], products: dict[int, str]) -> list[ProductRow]:
    rows: list[ProductRow] = []

    for item in items:
        product_id = item.get("id") or item.get("product_id")
        offer_id = item.get("offer_id")

        article = None
        if isinstance(offer_id, str) and offer_id:
            article = offer_id
        elif isinstance(product_id, int):
            article = products.get(product_id)

        if not article:
            continue

        length = _extract_dimension(item, "length")
        width = _extract_dimension(item, "width")
        height = _extract_dimension(item, "height")
        weight = _extract_weight(item)

        volume_cm3 = None
        if None not in (length, width, height):
            volume_cm3 = float(length * width * height)

        rows.append(
            ProductRow(
                article=article,
                volume_cm3=volume_cm3,
                weight=weight,
                length_cm=length,
                width_cm=width,
                height_cm=height,
            )
        )

    return rows


def save_csv(rows: list[ProductRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "артикул",
                "объем товара",
                "вес товара",
                "длина",
                "ширина",
                "высота",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.article,
                    f"{row.volume_cm3:.3f}" if row.volume_cm3 is not None else "",
                    f"{row.weight:.3f}" if row.weight is not None else "",
                    f"{row.length_cm:.3f}" if row.length_cm is not None else "",
                    f"{row.width_cm:.3f}" if row.width_cm is not None else "",
                    f"{row.height_cm:.3f}" if row.height_cm is not None else "",
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Парсер объемных характеристик товаров Ozon. "
            "Сохраняет CSV: артикул, объем товара, вес товара, длина, ширина, высота."
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args()


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


def main() -> None:
    load_dotenv()

    client_id = _clean_env_value("OZON_CLIENT_ID")
    api_key = _clean_env_value("OZON_API_KEY")

    args = parse_args()

    parser = OzonVolumeParser(client_id=client_id, api_key=api_key)

    products = parser.list_products(batch_size=args.batch_size)
    if not products:
        raise RuntimeError("Не удалось получить список товаров или список пуст.")

    product_ids = list(products.keys())

    all_items: list[dict[str, Any]] = []
    step = 1000
    for index in range(0, len(product_ids), step):
        chunk = product_ids[index : index + step]
        all_items.extend(parser.fetch_dimensions(chunk))

    rows = build_rows(all_items, products)
    save_csv(rows, args.output)

    print(f"Готово. Записано строк: {len(rows)}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
