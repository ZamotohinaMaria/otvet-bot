# Ozon API Worker (Tkinter)

Desktop utility for universal work with Ozon Seller API methods.

## Run

From repository root:

```bash
python api_worker/main.py
```

## Authentication

- App reads credentials from repository root `.env`.
- Required variables:
  - `OZON_CLIENT_ID`
  - `OZON_API_KEY`
- `.env` is read-only for this app workflow (no file writes).

## Current UI features

- HTTP method and endpoint editor
- API method string input
  - examples: `POST /v3/product/list`, `/v3/product/list`
- Searchable list of API methods with one-click apply
- JSON payload editor with formatting
- Request preview in dry-run mode
- Real HTTP calls to Ozon API when Dry-run is disabled
- Response view with status code, headers and JSON/text body
- Request history tab

## Structure

- `main.py` - entry point
- `auth.py` - load auth from root `.env`
- `api_client.py` - HTTP client and response parsing
- `method_catalog.py` - API method catalog and parser for method strings
- `config.py` - base constants
- `ui/app.py` - main window and handlers
- `ui/widgets.py` - reusable widgets
