"""Entry point so the package can be run as ``python -m app``."""

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main())
