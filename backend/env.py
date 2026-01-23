import os

from dotenv import dotenv_values


def load_environment() -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    env_filename = ".env.production" if app_env == "production" else ".env.local"

    base_values = dotenv_values(".env")
    env_values = dotenv_values(env_filename)
    merged = {**base_values, **env_values}

    for key, value in merged.items():
        if value is None:
            continue
        os.environ.setdefault(key, value)
