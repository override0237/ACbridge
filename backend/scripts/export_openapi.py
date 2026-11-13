"""Write the API contract to backend/openapi.json so the frontend can generate or check its client.

    python -m scripts.export_openapi
A test fails if the committed file is out of date, so backend and frontend cannot silently drift apart.
"""
import json
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")  # no database connection is needed to build the schema

from app.main import app  # noqa: E402

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render())
    print(f"Wrote {OUTPUT}")
