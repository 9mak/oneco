"""`python -m syndication_service.sns_publisher` のエントリポイント"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
