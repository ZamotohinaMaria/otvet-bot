import json
from dataclasses import dataclass
from typing import Any

import requests

from config import BASE_URL, DEFAULT_HEADERS


class OzonApiRequestError(RuntimeError):
    pass


@dataclass
class ApiCallResult:
    method: str
    url: str
    status_code: int
    reason: str
    elapsed_ms: int
    response_headers: dict[str, str]
    is_json: bool
    json_body: Any | None
    text_body: str


class OzonApiClient:
    def __init__(self, client_id: str, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                **DEFAULT_HEADERS,
                "Client-Id": client_id,
                "Api-Key": api_key,
            }
        )

    def call(
        self,
        method: str,
        endpoint: str,
        payload: Any,
        timeout_seconds: int,
    ) -> ApiCallResult:
        normalized_method = method.strip().upper()
        normalized_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{BASE_URL}{normalized_endpoint}"

        request_kwargs: dict[str, Any] = {"timeout": timeout_seconds}
        if normalized_method == "GET":
            if payload and not isinstance(payload, dict):
                raise OzonApiRequestError(
                    "Для GET payload должен быть JSON-объектом (словарем), "
                    "чтобы преобразовать его в query-параметры."
                )
            request_kwargs["params"] = payload or {}
        else:
            request_kwargs["json"] = payload

        try:
            response = self.session.request(normalized_method, url, **request_kwargs)
        except requests.RequestException as exc:
            raise OzonApiRequestError(f"Сетевая ошибка при запросе к Ozon API: {exc}") from exc

        elapsed_ms = int(response.elapsed.total_seconds() * 1000)
        content_type = (response.headers.get("Content-Type") or "").lower()
        text_body = response.text or ""
        is_json = "application/json" in content_type

        json_body: Any | None = None
        if is_json:
            try:
                json_body = response.json()
            except json.JSONDecodeError:
                is_json = False

        return ApiCallResult(
            method=normalized_method,
            url=url,
            status_code=response.status_code,
            reason=response.reason or "",
            elapsed_ms=elapsed_ms,
            response_headers=dict(response.headers),
            is_json=is_json,
            json_body=json_body,
            text_body=text_body,
        )

