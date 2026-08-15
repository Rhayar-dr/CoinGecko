"""Plain domain models (framework-agnostic).

These dataclasses represent the business concepts independently of how they are
transported (JSON) or stored (SQLAlchemy). Keeping them separate from the ORM
models decouples business logic from persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.errors import MissingFieldsError


@dataclass(frozen=True)
class CryptoHistory:
    """A single coin's price snapshot for one day."""

    coin_id: str
    date: date
    price_usd: float | None
    raw_json: dict[str, Any]

    @classmethod
    def from_api_response(
        cls, coin_id: str, on_date: date, payload: dict[str, Any]
    ) -> CryptoHistory:
        """Build a :class:`CryptoHistory` from a CoinGecko history payload.

        The USD price lives at ``market_data.current_price.usd``. For very old
        dates (or coins that did not yet trade) ``market_data`` may be absent;
        in that case ``price_usd`` is ``None`` and callers can decide how to
        react. A completely empty payload, however, signals a malformed
        response.
        """
        if not isinstance(payload, dict) or "id" not in payload:
            raise MissingFieldsError(
                f"Malformed CoinGecko response for {coin_id} on {on_date}: missing 'id'."
            )

        price_usd = (
            payload.get("market_data", {}).get("current_price", {}).get("usd")
            if isinstance(payload.get("market_data"), dict)
            else None
        )

        return cls(
            coin_id=coin_id,
            date=on_date,
            price_usd=float(price_usd) if price_usd is not None else None,
            raw_json=payload,
        )
