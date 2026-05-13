import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class OzonAuth:
    client_id: str
    api_key: str
    env_path: Path


def _clean_env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable is missing: {name}")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def load_auth_from_repo_env() -> OzonAuth:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    return OzonAuth(
        client_id=_clean_env_value("OZON_CLIENT_ID"),
        api_key=_clean_env_value("OZON_API_KEY"),
        env_path=env_path,
    )

