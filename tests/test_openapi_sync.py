import json
from pathlib import Path

from citetally.api import create_app
from citetally.config import Settings

OPENAPI_FILE = Path(__file__).resolve().parent.parent / "web" / "openapi.json"


def test_committed_openapi_matches_the_app() -> None:
    """The web app's generated types come from this file. Regenerate it after API changes:
    python -m tools.export_openapi, then npm run gen:api in web/."""
    committed = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    current = create_app(Settings(_env_file=None)).openapi()
    assert committed == json.loads(json.dumps(current))
