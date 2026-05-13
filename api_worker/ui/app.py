import json
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

from api_client import OzonApiClient, OzonApiRequestError
from auth import OzonAuth, load_auth_from_repo_env
from config import BASE_URL, DEFAULT_HEADERS, DEFAULT_METHOD, DEFAULT_TIMEOUT_SECONDS
from method_catalog import (
    ALL_METHODS,
    HTTP_METHODS,
    ApiMethod,
    find_best_method,
    get_method_brief,
    parse_method_input,
)
from ui.widgets import JsonText, ReadOnlyLog


class ApiWorkerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ozon API Worker")
        self.geometry("1300x820")
        self.minsize(1050, 680)

        self.auth: OzonAuth | None = None
        self.api_client: OzonApiClient | None = None
        self.catalog_filtered: list[ApiMethod] = []
        self._load_auth_or_warn()
        self._build_layout()
        self._refresh_method_catalog("")

    def _load_auth_or_warn(self) -> None:
        try:
            self.auth = load_auth_from_repo_env()
            self.api_client = OzonApiClient(
                client_id=self.auth.client_id,
                api_key=self.auth.api_key,
            )
        except Exception as exc:  # noqa: BLE001
            self.auth = None
            self.api_client = None
            messagebox.showwarning(
                "Auth from .env",
                "Could not load OZON_CLIENT_ID/OZON_API_KEY from root .env.\n"
                f"Details: {exc}",
            )

    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_tabs()

    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self, padding=12)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(6, weight=1)

        ttk.Label(sidebar, text="Authentication", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        env_path_text = str(self.auth.env_path) if self.auth else "not loaded"
        ttk.Label(sidebar, text=f".env path: {env_path_text}", wraplength=320).grid(
            row=1, column=0, sticky="w", pady=(0, 6)
        )

        auth_ok = self.auth is not None
        status_color = "#1b5e20" if auth_ok else "#b71c1c"
        status_text = "Loaded from .env" if auth_ok else "Missing values in .env"
        ttk.Label(sidebar, text=status_text, foreground=status_color).grid(
            row=2, column=0, sticky="w", pady=(0, 10)
        )

        self.client_id_view = ttk.Entry(sidebar, state="readonly")
        self.client_id_view.grid(row=3, column=0, sticky="ew", pady=2)
        self.api_key_view = ttk.Entry(sidebar, state="readonly")
        self.api_key_view.grid(row=4, column=0, sticky="ew", pady=2)
        self._render_masked_auth_values()

        ttk.Button(sidebar, text="Reload .env", command=self._reload_auth).grid(
            row=5, column=0, sticky="w", pady=(8, 8)
        )

        self.dry_run = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            sidebar,
            text="Dry-run (do not send request)",
            variable=self.dry_run,
        ).grid(row=6, column=0, sticky="sw")

    def _render_masked_auth_values(self) -> None:
        client_value = self._mask_secret(self.auth.client_id) if self.auth else ""
        api_key_value = self._mask_secret(self.auth.api_key) if self.auth else ""
        self._set_readonly_entry(self.client_id_view, f"Client-Id: {client_value}")
        self._set_readonly_entry(self.api_key_view, f"Api-Key: {api_key_value}")

    @staticmethod
    def _set_readonly_entry(entry: ttk.Entry, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.configure(state="readonly")

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 6:
            return "*" * len(value)
        return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"

    def _reload_auth(self) -> None:
        self._load_auth_or_warn()
        self._render_masked_auth_values()

    def _build_main_tabs(self) -> None:
        main_area = ttk.Frame(self, padding=(0, 12, 12, 12))
        main_area.grid(row=0, column=1, sticky="nsew")
        main_area.columnconfigure(0, weight=1)
        main_area.rowconfigure(0, weight=1)

        self.tabs = ttk.Notebook(main_area)
        self.tabs.grid(row=0, column=0, sticky="nsew")

        self.request_tab = ttk.Frame(self.tabs, padding=12)
        self.response_tab = ttk.Frame(self.tabs, padding=12)
        self.history_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.request_tab, text="Request")
        self.tabs.add(self.response_tab, text="Response")
        self.tabs.add(self.history_tab, text="History")

        self._build_request_tab()
        self._build_response_tab()
        self._build_history_tab()

    def _build_request_tab(self) -> None:
        self.request_tab.columnconfigure(1, weight=1)
        self.request_tab.rowconfigure(6, weight=1)

        ttk.Label(self.request_tab, text="HTTP method").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.http_method_var = tk.StringVar(value=DEFAULT_METHOD)
        self.http_method_combo = ttk.Combobox(
            self.request_tab,
            state="readonly",
            textvariable=self.http_method_var,
            values=HTTP_METHODS,
            width=10,
        )
        self.http_method_combo.grid(row=0, column=1, sticky="w")
        self.http_method_combo.bind("<<ComboboxSelected>>", self._on_http_method_change)

        ttk.Label(self.request_tab, text="Endpoint").grid(
            row=1, column=0, sticky="w", pady=(10, 6)
        )
        self.endpoint_entry = ttk.Entry(self.request_tab)
        self.endpoint_entry.grid(row=1, column=1, sticky="ew", pady=(10, 6))

        method_input_frame = ttk.Frame(self.request_tab)
        method_input_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        method_input_frame.columnconfigure(1, weight=1)
        ttk.Label(method_input_frame, text="API method string").grid(row=0, column=0, sticky="w")
        self.api_method_input = ttk.Entry(method_input_frame)
        self.api_method_input.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(
            method_input_frame, text="Apply string", command=self._apply_method_string
        ).grid(row=0, column=2, sticky="e")
        ttk.Label(
            method_input_frame,
            text='Format: "POST /v3/product/list" or "/v3/product/list"',
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        catalog_frame = ttk.LabelFrame(self.request_tab, text="All API methods")
        catalog_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(4, 8))
        catalog_frame.columnconfigure(0, weight=1)
        catalog_frame.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(catalog_frame)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search").grid(row=0, column=0, sticky="w")
        self.method_search_var = tk.StringVar()
        self.method_search_var.trace_add("write", self._on_method_search_change)
        self.method_search_entry = ttk.Entry(search_frame, textvariable=self.method_search_var)
        self.method_search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(search_frame, text="Clear", command=lambda: self.method_search_var.set("")).grid(
            row=0, column=2, sticky="e"
        )

        list_wrap = ttk.Frame(catalog_frame)
        list_wrap.grid(row=1, column=0, sticky="nsew")
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)
        self.methods_listbox = tk.Listbox(list_wrap, exportselection=False, height=12)
        self.methods_listbox.grid(row=0, column=0, sticky="nsew")
        methods_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.methods_listbox.yview)
        methods_scroll.grid(row=0, column=1, sticky="ns")
        self.methods_listbox.configure(yscrollcommand=methods_scroll.set)
        self.methods_listbox.bind("<<ListboxSelect>>", self._on_select_method)
        self.methods_listbox.bind("<Double-1>", self._on_double_click_method)

        ttk.Button(
            catalog_frame, text="Use selected method", command=self._apply_selected_method
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        info_frame = ttk.LabelFrame(self.request_tab, text="Method description")
        info_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        info_frame.columnconfigure(0, weight=1)
        self.method_info_label = ttk.Label(
            info_frame,
            text="Выберите метод, чтобы увидеть краткое описание.",
            wraplength=900,
            justify="left",
        )
        self.method_info_label.grid(row=0, column=0, sticky="ew", padx=8, pady=8)

        payload_header = ttk.Frame(self.request_tab)
        payload_header.grid(row=5, column=0, columnspan=2, sticky="ew")
        payload_header.columnconfigure(2, weight=1)
        ttk.Label(payload_header, text="JSON payload").grid(row=0, column=0, sticky="w")
        ttk.Label(payload_header, text="Timeout (sec)").grid(row=0, column=1, sticky="e", padx=(20, 8))
        self.timeout_var = tk.IntVar(value=DEFAULT_TIMEOUT_SECONDS)
        self.timeout_spin = ttk.Spinbox(
            payload_header, from_=1, to=300, textvariable=self.timeout_var, width=6
        )
        self.timeout_spin.grid(row=0, column=2, sticky="w")

        self.payload_text = JsonText(self.request_tab)
        self.payload_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(8, 10))

        actions = ttk.Frame(self.request_tab)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="Format JSON", command=self._format_payload_json).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(actions, text="Send request", command=self._handle_send).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

    def _build_response_tab(self) -> None:
        self.response_tab.columnconfigure(0, weight=1)
        self.response_tab.rowconfigure(0, weight=1)
        self.response_log = ReadOnlyLog(self.response_tab)
        self.response_log.grid(row=0, column=0, sticky="nsew")

    def _build_history_tab(self) -> None:
        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(0, weight=1)
        self.history_log = ReadOnlyLog(self.history_tab)
        self.history_log.grid(row=0, column=0, sticky="nsew")

    def _on_method_search_change(self, *_args) -> None:
        query = self.method_search_var.get().strip()
        self._refresh_method_catalog(query)

    def _on_http_method_change(self, _event) -> None:
        query = self.method_search_var.get().strip()
        self._refresh_method_catalog(query)

    def _refresh_method_catalog(self, query: str) -> None:
        selected_http_method = self.http_method_var.get().strip().upper()
        q = query.lower()
        self.catalog_filtered = []
        for item in ALL_METHODS:
            if selected_http_method in HTTP_METHODS and item.http_method != selected_http_method:
                continue
            if q and not (
                q in item.http_method.lower()
                or q in item.endpoint.lower()
                or q in item.title.lower()
                or q in item.category.lower()
            ):
                continue
            self.catalog_filtered.append(item)

        self.methods_listbox.delete(0, "end")
        for item in self.catalog_filtered:
            self.methods_listbox.insert("end", item.display)

        if self.catalog_filtered:
            self.methods_listbox.selection_set(0)
            self.methods_listbox.activate(0)
            self._update_method_info(self.catalog_filtered[0])
        else:
            self.method_info_label.configure(
                text="Для выбранного HTTP-метода и фильтра ничего не найдено."
            )

    def _on_select_method(self, _event) -> None:
        selection = self.methods_listbox.curselection()
        if not selection:
            return
        method_item = self.catalog_filtered[selection[0]]
        self._update_method_info(method_item)

    def _on_double_click_method(self, _event) -> None:
        self._apply_selected_method()

    def _apply_selected_method(self) -> None:
        selection = self.methods_listbox.curselection()
        if not selection:
            messagebox.showinfo("Method selection", "Select an API method from the list.")
            return
        index = selection[0]
        method_item = self.catalog_filtered[index]
        self._apply_method_item(method_item)

    def _apply_method_item(self, method_item: ApiMethod) -> None:
        self.http_method_var.set(method_item.http_method)
        self.endpoint_entry.delete(0, "end")
        self.endpoint_entry.insert(0, method_item.endpoint)
        if method_item.payload:
            self.payload_text.set_all(method_item.payload)
        self._update_method_info(method_item)

    def _apply_method_string(self) -> None:
        raw = self.api_method_input.get().strip()
        try:
            http_method, endpoint = parse_method_input(raw, self.http_method_var.get())
        except ValueError as exc:
            messagebox.showerror("Method parse error", str(exc))
            return
        self.http_method_var.set(http_method)
        self.endpoint_entry.delete(0, "end")
        self.endpoint_entry.insert(0, endpoint)
        best_match = find_best_method(http_method, endpoint)
        if best_match is not None:
            self._refresh_method_catalog(self.method_search_var.get().strip())
            self._update_method_info(best_match)
            self._select_method_in_list(best_match)
        else:
            self.method_info_label.configure(
                text=(
                    f"Метод: {http_method} {endpoint}\n"
                    "Описание: пользовательский endpoint, введен вручную.\n"
                    "Что получите: точная структура ответа зависит от документации Ozon."
                )
            )

    def _select_method_in_list(self, method_item: ApiMethod) -> None:
        for index, candidate in enumerate(self.catalog_filtered):
            if (
                candidate.http_method == method_item.http_method
                and candidate.endpoint == method_item.endpoint
            ):
                self.methods_listbox.selection_clear(0, "end")
                self.methods_listbox.selection_set(index)
                self.methods_listbox.activate(index)
                self.methods_listbox.see(index)
                return

    def _update_method_info(self, method_item: ApiMethod) -> None:
        summary, response_hint = get_method_brief(method_item)
        self.method_info_label.configure(
            text=(
                f"Метод: {method_item.http_method} {method_item.endpoint}\n"
                f"Что делает: {summary}\n"
                f"Что получите: {response_hint}"
            )
        )

    def _format_payload_json(self) -> None:
        raw_payload = self.payload_text.get_all()
        if not raw_payload:
            self.payload_text.set_all("{}")
            return
        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            messagebox.showerror("JSON error", f"Cannot parse JSON:\n{exc}")
            return
        self.payload_text.set_all(json.dumps(parsed, ensure_ascii=False, indent=2))

    def _handle_send(self) -> None:
        if self.auth is None or self.api_client is None:
            messagebox.showerror(
                "Auth required",
                "Cannot build request because OZON_CLIENT_ID/OZON_API_KEY were not loaded from .env.",
            )
            return

        http_method = self.http_method_var.get().strip().upper() or DEFAULT_METHOD
        endpoint = self.endpoint_entry.get().strip()
        timeout_seconds = self.timeout_var.get()
        raw_payload = self.payload_text.get_all() or "{}"

        if not endpoint:
            messagebox.showwarning("Endpoint required", "Provide endpoint, e.g. /v3/product/list")
            return
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            messagebox.showerror("JSON error", f"Check payload:\n{exc}")
            return

        headers = dict(DEFAULT_HEADERS)
        headers["Client-Id"] = self.auth.client_id
        headers["Api-Key"] = self.auth.api_key

        preview = {
            "mode": "dry-run" if self.dry_run.get() else "send-real-request",
            "method": http_method,
            "url": f"{BASE_URL}{endpoint}",
            "timeout_seconds": timeout_seconds,
            "headers": {
                "Content-Type": headers["Content-Type"],
                "Client-Id": self._mask_secret(headers["Client-Id"]),
                "Api-Key": self._mask_secret(headers["Api-Key"]),
            },
            "payload": payload,
        }
        pretty_preview = json.dumps(preview, ensure_ascii=False, indent=2)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.response_log.append(f"[{timestamp}] Request prepared:\n{pretty_preview}\n")
        self.history_log.append(f"[{timestamp}] {http_method} {endpoint} | dry_run={self.dry_run.get()}")

        if self.dry_run.get():
            self.response_log.append(
                "Dry-run is enabled: request was not sent.\n"
                "Выключите Dry-run, чтобы отправить реальный запрос."
            )
        else:
            try:
                result = self.api_client.call(
                    method=http_method,
                    endpoint=endpoint,
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
            except OzonApiRequestError as exc:
                self.response_log.append(f"Ошибка отправки запроса: {exc}")
                self.history_log.append(
                    f"[{timestamp}] {http_method} {endpoint} | error={str(exc)}"
                )
                self.tabs.select(self.response_tab)
                return

            response_block: dict[str, object] = {
                "status_code": result.status_code,
                "reason": result.reason,
                "elapsed_ms": result.elapsed_ms,
                "url": result.url,
                "response_headers": result.response_headers,
                "body": result.json_body if result.is_json else result.text_body,
            }
            pretty_response = json.dumps(response_block, ensure_ascii=False, indent=2)
            self.response_log.append(f"[{timestamp}] Response received:\n{pretty_response}\n")
            self.history_log.append(
                f"[{timestamp}] {http_method} {endpoint} | status={result.status_code}"
            )

        self.tabs.select(self.response_tab)
