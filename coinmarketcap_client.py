"""Small client for the CoinMarketCap listings API."""

from __future__ import annotations

from typing import Iterable

import requests


DEFAULT_EXCLUDED_SYMBOLS = frozenset(
    {
        # Stablecoins and fiat-backed tokens should not enter a market-cap index.
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "TUSD",
        "USDP",
        "PYUSD",
        "EURC",
        # Wrapped BTC is not an independent crypto asset for this strategy.
        "WBTC",
    }
)
LARGE_CAP = 20
MID_CAP = 50
SMALL_CAP = 100
LISTINGS_URL = "https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest"


class CoinMarketCapClient:
    """Retrieve investable assets ranked by CoinMarketCap market-cap rank."""

    def __init__(
        self,
        api_key: str,
        *,
        ignore_list: Iterable[str] = (),
        session: requests.Session | None = None,
        timeout: float = 20,
        listings_url: str = LISTINGS_URL,
    ) -> None:
        if not api_key:
            raise ValueError("A CoinMarketCap API key is required")

        self.ignore_list = DEFAULT_EXCLUDED_SYMBOLS | frozenset(ignore_list)
        self._api_key = api_key
        self._session = session or requests.Session()
        self._timeout = timeout
        self._listings_url = listings_url
        self.sorted_listing = self._fetch_listings(
            limit=SMALL_CAP + len(self.ignore_list)
        )

    def _fetch_listings(self, *, limit: int) -> list[str]:
        response = self._session.get(
            self._listings_url,
            headers={"Accept": "application/json", "X-CMC_PRO_API_KEY": self._api_key},
            params={"start": 1, "limit": limit, "convert": "USD"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status", {})
        if str(status.get("error_code", "0")) != "0":
            raise RuntimeError(
                "CoinMarketCap listings request failed: {}".format(
                    status.get("error_message", status.get("error_code"))
                )
            )

        listings = sorted(
            payload.get("data", []), key=lambda item: item.get("cmc_rank", float("inf"))
        )
        return [
            item["symbol"]
            for item in listings
            if item.get("symbol") and item["symbol"] not in self.ignore_list
        ]

    def getTopK(self, k: int) -> list[str]:
        if k < 0:
            raise ValueError("k must be non-negative")
        return self.sorted_listing[:k]

    def getLargeCap(self) -> list[str]:
        return self.getTopK(LARGE_CAP)

    def getMidCap(self) -> list[str]:
        return self.sorted_listing[LARGE_CAP:MID_CAP]

    def getSmallCap(self) -> list[str]:
        return self.sorted_listing[MID_CAP:SMALL_CAP]
