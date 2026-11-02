"""Run the API: python -m citetally. Always binds to 127.0.0.1 (single-user, local)."""

import uvicorn

from citetally.api import create_app
from citetally.config import Settings


def main() -> None:
    settings = Settings()
    # No access log: it prints the whole address, and the inbox search puts what the person typed
    # (a vendor, an invoice number) in the address. Audit events carry the request id instead.
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
