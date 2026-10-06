"""Export the OpenAPI document: ``python -m finpulse.openapi <output-path>``.

The exported file in ``packages/contracts`` is the shared contract the web app's TypeScript
types are generated from. CI regenerates it and fails if the committed copy is stale.
"""

import json
import sys
from pathlib import Path

from finpulse.config import Settings
from finpulse.main import create_app


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m finpulse.openapi <output-path>")
    # Development settings so the docs routes (and therefore the schema) are enabled.
    app = create_app(Settings(FINPULSE_ENV="development", LOG_FORMAT="console"))
    schema = app.openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
