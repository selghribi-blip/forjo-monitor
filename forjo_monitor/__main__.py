"""Allow ``python -m forjo_monitor``."""

from __future__ import annotations

import sys

from forjo_monitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
