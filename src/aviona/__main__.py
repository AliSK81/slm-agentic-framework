"""Allow ``python -m aviona`` when the console script is stale or locked."""

from __future__ import annotations

import sys

from aviona.cli import main

if __name__ == "__main__":
    sys.exit(main())
