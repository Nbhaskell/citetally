"""Run the API: python -m citetally. Always binds to 127.0.0.1 (single-user, local)."""

import uvicorn

from citetally.api import create_app
from citetally.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port)


if __name__ == "__main__":
    main()
