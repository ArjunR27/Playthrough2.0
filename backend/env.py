import os
from pathlib import Path

from dotenv import dotenv_values


def load_environment() -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    env_filename = ".env.production" if app_env == "production" else ".env.local"

    repo_root = Path(__file__).resolve().parents[1]
    base_values = dotenv_values(repo_root / ".env")
    env_values = dotenv_values(repo_root / env_filename)
    merged = {**base_values, **env_values}

    for key, value in merged.items():
        if value is None:
            continue
        os.environ.setdefault(key, value)
