"""``python -m finpulse`` — run the API with settings from the environment."""

import uvicorn

from finpulse.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "finpulse.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_config=None,  # logging is configured by the app itself
    )


if __name__ == "__main__":
    main()
