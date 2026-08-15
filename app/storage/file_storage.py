"""Local file storage for the raw CoinGecko responses.

The raw JSON is persisted verbatim so the original data can always be
re-processed later. Files are laid out per coin with the date in the filename,
as required by the exam::

    data/
    └── bitcoin/
        ├── bitcoin_2017-12-30.json
        └── bitcoin_2017-12-31.json
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.utils.dates import to_iso

logger = logging.getLogger(__name__)


class FileStorage:
    """Persists raw API payloads as JSON files on the local filesystem."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def path_for(self, coin_id: str, on_date: date) -> Path:
        """Return the target path for a given coin/date, without touching disk."""
        return self._base_dir / coin_id / f"{coin_id}_{to_iso(on_date)}.json"

    def save(self, coin_id: str, on_date: date, payload: dict[str, Any]) -> Path:
        """Write ``payload`` to ``<data_dir>/<coin>/<coin>_<date>.json``.

        Returns:
            The path the file was written to.
        """
        target = self.path_for(coin_id, on_date)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically via a temp file + rename so a crash mid-write never
        # leaves a truncated JSON file behind.
        tmp = target.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.replace(target)

        logger.info("File saved: %s", target)
        return target
