"""Write the API's OpenAPI schema to web/openapi.json (the source for generated web types).

Run from the repository root: python -m tools.export_openapi
"""

import json
from pathlib import Path

from citetally.api import create_app
from citetally.config import Settings

OPENAPI_FILE = Path(__file__).resolve().parent.parent / "web" / "openapi.json"


def main() -> None:
    schema = create_app(Settings(_env_file=None)).openapi()
    OPENAPI_FILE.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OPENAPI_FILE}")


if __name__ == "__main__":
    main()
