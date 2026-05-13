from dataclasses import dataclass


@dataclass(frozen=True)
class ApiMethod:
    http_method: str
    endpoint: str
    title: str
    category: str
    payload: str = "{}"
    summary: str = ""
    response_hint: str = ""

    @property
    def display(self) -> str:
        return f"{self.http_method} {self.endpoint} | {self.category} | {self.title}"


HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


BASE_METHODS: list[ApiMethod] = [
    ApiMethod("POST", "/v3/product/list", "Product list", "Products", '{\n  "filter": {"visibility": "ALL"},\n  "last_id": "",\n  "limit": 100\n}'),
    ApiMethod("POST", "/v2/product/list", "Product list v2", "Products", '{\n  "filter": {"visibility": "ALL"},\n  "last_id": "",\n  "limit": 100\n}'),
    ApiMethod("POST", "/v2/product/import", "Import products", "Products", '{\n  "items": []\n}'),
    ApiMethod("POST", "/v1/product/import-by-sku", "Import by SKU", "Products", '{\n  "items": []\n}'),
    ApiMethod("POST", "/v2/product/info", "Product info", "Products", '{\n  "product_id": [123456789]\n}'),
    ApiMethod("POST", "/v3/product/info/list", "Product info list v3", "Products", '{\n  "product_id": [123456789]\n}'),
    ApiMethod("POST", "/v2/product/info/list", "Product info list v2", "Products", '{\n  "product_id": [123456789]\n}'),
    ApiMethod("POST", "/v1/product/info/description", "Product description", "Products", '{\n  "product_id": 123456789\n}'),
    ApiMethod("POST", "/v1/product/import/prices", "Import prices", "Prices", '{\n  "prices": []\n}'),
    ApiMethod("POST", "/v4/product/info/prices", "Product prices info", "Prices", '{\n  "filter": {"offer_id": [], "product_id": []},\n  "limit": 100,\n  "cursor": ""\n}'),
    ApiMethod("POST", "/v1/product/import/stocks", "Import stocks", "Stocks", '{\n  "stocks": []\n}'),
    ApiMethod("POST", "/v3/products/info/attributes", "Product attributes v3", "Products", '{\n  "filter": {"product_id": [123456789], "visibility": "ALL"},\n  "limit": 100,\n  "sort_dir": "ASC"\n}'),
    ApiMethod("POST", "/v4/product/info/attributes", "Product attributes v4", "Products", '{\n  "filter": {"product_id": [123456789], "visibility": "ALL"},\n  "limit": 100,\n  "sort_dir": "ASC"\n}'),
    ApiMethod("POST", "/v1/description-category/tree", "Category tree", "Categories", "{}"),
    ApiMethod("POST", "/v1/description-category/attribute", "Category attributes", "Categories", '{\n  "description_category_id": 0,\n  "type_id": 0\n}'),
    ApiMethod("POST", "/v1/description-category/attribute/values", "Attribute values", "Categories", '{\n  "attribute_id": 0,\n  "description_category_id": 0,\n  "limit": 100,\n  "last_value_id": 0\n}'),
    ApiMethod("POST", "/v1/description-category/attribute/values/search", "Search attribute values", "Categories", '{\n  "attribute_id": 0,\n  "description_category_id": 0,\n  "value": ""\n}'),
    ApiMethod("POST", "/v1/warehouse/list", "Warehouse list", "Warehouse", "{}"),
    ApiMethod("POST", "/v1/delivery-method/list", "Delivery methods", "Warehouse", "{}"),
    ApiMethod("POST", "/v3/posting/fbs/list", "FBS posting list", "FBS", '{\n  "dir": "ASC",\n  "filter": {"since": "2026-01-01T00:00:00.000Z", "to": "2026-01-02T00:00:00.000Z"},\n  "limit": 100,\n  "offset": 0,\n  "with": {"analytics_data": false, "barcodes": false, "financial_data": false}\n}'),
    ApiMethod("POST", "/v3/posting/fbs/get", "FBS posting by number", "FBS", '{\n  "posting_number": "",\n  "with": {"analytics_data": true, "barcodes": true, "financial_data": true}\n}'),
    ApiMethod("POST", "/v3/posting/fbs/unfulfilled/list", "FBS unfulfilled list", "FBS", '{\n  "dir": "ASC",\n  "filter": {"cutoff_from": "2026-01-01T00:00:00Z", "cutoff_to": "2026-01-02T00:00:00Z"},\n  "limit": 100,\n  "offset": 0,\n  "with": {"analytics_data": false, "barcodes": false, "financial_data": false}\n}'),
    ApiMethod("POST", "/v2/fbs/posting/delivering", "Mark delivering", "FBS", '{\n  "posting_number": [],\n  "provider_id": 0\n}'),
    ApiMethod("POST", "/v2/fbs/posting/last-mile", "Set last-mile", "FBS", '{\n  "posting_number": "",\n  "tracking_number": ""\n}'),
    ApiMethod("POST", "/v2/fbs/posting/delivered", "Mark delivered", "FBS", '{\n  "posting_number": []\n}'),
    ApiMethod("POST", "/v2/fbs/posting/tracking-number/set", "Set tracking number", "FBS", '{\n  "posting_number": "",\n  "tracking_number": ""\n}'),
    ApiMethod("POST", "/v3/posting/fbs/ship", "Ship FBS v3", "FBS", '{\n  "packages": [],\n  "posting_number": ""\n}'),
    ApiMethod("POST", "/v4/posting/fbs/ship", "Ship FBS v4", "FBS", '{\n  "packages": [],\n  "posting_number": ""\n}'),
    ApiMethod("POST", "/v1/review/list", "Review list", "Reviews", '{\n  "limit": 100,\n  "sort_by": "REVIEW_SORT_BY_CREATE_AT",\n  "sort_dir": "DESC",\n  "filter": {}\n}'),
    ApiMethod("POST", "/v1/review/comment/create", "Create review comment", "Reviews", '{\n  "review_uuid": "",\n  "text": ""\n}'),
]


def _expand_catalog_with_http_variants(base_methods: list[ApiMethod]) -> list[ApiMethod]:
    expanded: list[ApiMethod] = list(base_methods)
    existing_pairs = {(item.http_method, item.endpoint) for item in base_methods}
    endpoint_to_payload: dict[str, str] = {}
    endpoint_to_title: dict[str, str] = {}
    endpoint_to_category: dict[str, str] = {}
    endpoint_to_summary: dict[str, str] = {}
    endpoint_to_response_hint: dict[str, str] = {}

    for item in base_methods:
        endpoint_to_payload[item.endpoint] = item.payload
        endpoint_to_title[item.endpoint] = item.title
        endpoint_to_category[item.endpoint] = item.category
        endpoint_to_summary[item.endpoint] = item.summary
        endpoint_to_response_hint[item.endpoint] = item.response_hint

    for endpoint, payload in endpoint_to_payload.items():
        for http_method in HTTP_METHODS:
            pair = (http_method, endpoint)
            if pair in existing_pairs:
                continue
            expanded.append(
                ApiMethod(
                    http_method=http_method,
                    endpoint=endpoint,
                    title=f"{endpoint_to_title[endpoint]} ({http_method} variant)",
                    category=f"{endpoint_to_category[endpoint]} / manual",
                    payload=payload,
                    summary=endpoint_to_summary[endpoint],
                    response_hint=endpoint_to_response_hint[endpoint],
                )
            )

    return sorted(expanded, key=lambda x: (x.endpoint, HTTP_METHODS.index(x.http_method)))


ALL_METHODS: list[ApiMethod] = _expand_catalog_with_http_variants(BASE_METHODS)


def get_method_brief(api_method: ApiMethod) -> tuple[str, str]:
    summary = api_method.summary.strip()
    response_hint = api_method.response_hint.strip()

    if summary and response_hint:
        return summary, response_hint

    endpoint = api_method.endpoint
    category = api_method.category.lower()

    if not summary:
        if "/list" in endpoint:
            summary = "Возвращает список сущностей с фильтрами и пагинацией."
        elif "/import" in endpoint:
            summary = "Импортирует или обновляет данные в Ozon."
        elif "/info" in endpoint or "/attributes" in endpoint:
            summary = "Возвращает подробную информацию и атрибуты по выбранным сущностям."
        elif "/review" in endpoint:
            summary = "Работает с отзывами и ответами продавца."
        elif "/posting" in endpoint or "fbs" in category:
            summary = "Работает с отправлениями FBS и их статусами."
        else:
            summary = "Выполняет API-операцию для выбранного endpoint."

    if not response_hint:
        if "/list" in endpoint:
            response_hint = "Обычно содержит массив result.items и поля пагинации."
        elif "/import" in endpoint:
            response_hint = "Обычно возвращает статус операции, задачу или результаты по элементам."
        elif "/review" in endpoint:
            response_hint = "Обычно возвращает отзывы и/или статус ответа в объекте result."
        elif "/posting" in endpoint:
            response_hint = "Обычно возвращает данные отправлений, их статусы и связанную метаинформацию."
        else:
            response_hint = "Обычно возвращает объект result с полями, зависящими от метода."

    return summary, response_hint


def find_best_method(http_method: str, endpoint: str) -> ApiMethod | None:
    method = (http_method or "").strip().upper()
    path = (endpoint or "").strip()
    if not path.startswith("/"):
        path = f"/{path}" if path else path

    exact = next(
        (item for item in ALL_METHODS if item.http_method == method and item.endpoint == path),
        None,
    )
    if exact is not None:
        return exact

    # Fallback by endpoint if exact HTTP variant was not found.
    return next((item for item in ALL_METHODS if item.endpoint == path), None)


def parse_method_input(raw: str, fallback_http_method: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Строка метода API пустая")

    parts = text.split()
    if len(parts) == 1:
        endpoint = parts[0].strip()
        method = fallback_http_method.strip().upper() or "POST"
    else:
        method_candidate = parts[0].strip().upper()
        if method_candidate not in HTTP_METHODS:
            raise ValueError("HTTP-метод должен быть одним из: GET, POST, PUT, PATCH, DELETE")
        method = method_candidate
        endpoint = " ".join(parts[1:]).strip()

    if not endpoint:
        raise ValueError("Endpoint пустой")
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"

    return method, endpoint
