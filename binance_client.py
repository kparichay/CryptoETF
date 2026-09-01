"""Binance Spot adapter used by :mod:`index_fund`.

Quantities accepted by ``buyOrder`` and ``sellOrder`` are values in the quote
currency (normally USDT), not units of the asset being bought or sold.
"""

from __future__ import annotations

import time
from decimal import Decimal, ROUND_DOWN
from typing import Any

from binance.client import Client


MAX_ORDER_WAIT_SECONDS = 120
ORDER_POLL_SECONDS = 2
DEFAULT_FEE = 0.001
DEFAULT_QUOTE_ASSETS = ("USDT", "USDC", "FDUSD", "BTC", "ETH")
BULL = "UP"
BEAR = "DOWN"


class BinanceClient:
    """Adapter for Binance Spot market data, balances, and market orders."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        tld: str = "com",
        testnet: bool = False,
        client: Client | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise ValueError("Binance api_key and secret_key are required")
        self.client = client or Client(api_key, secret_key, tld=tld, testnet=testnet)
        self.testnet = testnet
        self.info: dict[str, Any] | None = None
        self.balance: list[dict[str, str]] = []
        self.all_symbols: set[str] = set()
        self._verify_status()
        self._refresh_market_metadata()
        self.fees = self._load_fees()

    def _verify_status(self) -> None:
        if hasattr(self.client, "get_system_status"):
            self.system_status = self.client.get_system_status()
            if self.system_status["status"] != 0:
                raise RuntimeError(
                    "Binance system status is {}".format(self.system_status["msg"])
                )
        if hasattr(self.client, "get_account_status"):
            self.account_status = self.client.get_account_status()
            if self.account_status["data"] != "Normal":
                raise RuntimeError("Binance account status is not Normal")

    def _refresh_market_metadata(self) -> None:
        exchange_info = self.client.get_exchange_info()
        self.all_pairs_info = exchange_info
        symbols = [
            item
            for item in exchange_info["symbols"]
            if item.get("status", "TRADING") == "TRADING"
        ]
        self.pair_info = {item["symbol"]: item for item in symbols}
        self.all_pairs = {
            item["symbol"]: float(item["price"])
            for item in self.client.get_all_tickers()
            if item["symbol"] in self.pair_info and float(item["price"]) > 0
        }
        self.all_symbols = {
            asset
            for item in self.pair_info.values()
            for asset in (item["baseAsset"], item["quoteAsset"])
        }
        quote_counts: dict[str, int] = {}
        for item in self.pair_info.values():
            quote = item["quoteAsset"]
            quote_counts[quote] = quote_counts.get(quote, 0) + 1
        ranked_quotes = sorted(
            quote_counts, key=lambda asset: quote_counts[asset], reverse=True
        )
        self.base_symbols = [
            asset for asset in DEFAULT_QUOTE_ASSETS if asset in quote_counts
        ]
        self.base_symbols.extend(
            asset for asset in ranked_quotes if asset not in self.base_symbols
        )

    def _refresh_balance(self) -> None:
        self.info = self.client.get_account()
        self.full_balance = self.info["balances"]
        self.balance = [
            item for item in self.info["balances"] if float(item["free"]) > 0
        ]

    def _load_fees(self) -> dict[str, float]:
        """Use per-symbol maker fees when the account endpoint permits it."""
        try:
            fees = self.client.get_trade_fee()
        except (AttributeError, OSError):
            return {}
        return {
            item["symbol"]: float(item["makerCommission"])
            for item in fees
            if float(item["makerCommission"]) > 0
        }

    def _fee(self, pair: str) -> float:
        return self.fees.get(pair, DEFAULT_FEE)

    def _pair_price(self, asset: str, quote: str) -> float:
        if asset == quote:
            return 1.0
        direct = asset + quote
        inverse = quote + asset
        if direct in self.all_pairs:
            return self.all_pairs[direct]
        if inverse in self.all_pairs:
            return 1.0 / self.all_pairs[inverse]
        raise ValueError("No price is available for {} in {}".format(asset, quote))

    def _price_in_quote(self, asset: str, quote: str) -> float:
        try:
            return self._pair_price(asset, quote)
        except ValueError:
            for bridge in self.base_symbols:
                if bridge in (asset, quote):
                    continue
                try:
                    return self._pair_price(asset, bridge) * self._pair_price(
                        bridge, quote
                    )
                except ValueError:
                    continue
        raise ValueError(
            "No supported price route is available for {} in {}".format(asset, quote)
        )

    def getUsdSymbol(self) -> str:
        return "USDT"

    def getPairPrice(self, symbol: str, base: str) -> float:
        return self._price_in_quote(symbol, base)

    def getPortfolioUsd(
        self, portfolio: list[tuple[str, float | str]]
    ) -> list[tuple[str, float]]:
        return [
            (asset, float(amount) * self._price_in_quote(asset, self.getUsdSymbol()))
            for asset, amount in portfolio
        ]

    def getBalanceUsd(
        self, cached: bool = True, ignore_small_amounts: float = 20
    ) -> list[tuple[str, float]]:
        if not cached or self.info is None:
            self._refresh_balance()
        valued = []
        for item in self.balance:
            try:
                value = float(item["free"]) * self._price_in_quote(
                    item["asset"], self.getUsdSymbol()
                )
            except ValueError:
                continue
            if value > ignore_small_amounts:
                valued.append((item["asset"], value))
        self.balance_usd = sorted(valued, key=lambda item: item[1], reverse=True)
        return self.balance_usd

    def _leveraged_assets(self, side: str) -> set[str]:
        assets = set()
        for pair in self.pair_info.values():
            asset = pair["baseAsset"]
            quote = pair["quoteAsset"]
            if asset.endswith(side) and asset[: -len(side)] + quote in self.pair_info:
                assets.add(asset[: -len(side)])
        return assets

    def getLeveragedCurrencies(self) -> list[str]:
        """Return assets with both UP and DOWN Spot tokens."""
        return sorted(self._leveraged_assets(BULL) & self._leveraged_assets(BEAR))

    def _leveraged_symbol(self, symbol: str, side: str) -> str:
        if symbol not in self.all_symbols:
            raise ValueError("Given symbol {} is not supported".format(symbol))
        if symbol not in self.getLeveragedCurrencies():
            raise ValueError("Given symbol {} cannot be leveraged".format(symbol))
        return symbol + side

    def getBullSymbol(self, symbol: str) -> str:
        return self._leveraged_symbol(symbol, BULL)

    def getBearSymbol(self, symbol: str) -> str:
        return self._leveraged_symbol(symbol, BEAR)

    def getDeleveragizedSymbol(self, symbol: str) -> str:
        """Return the base asset for an UP/DOWN token (legacy public spelling)."""
        if symbol.endswith(BULL):
            return symbol[: -len(BULL)]
        if symbol.endswith(BEAR):
            return symbol[: -len(BEAR)]
        return symbol

    def findBaseCurrency(
        self, portfolio: list[tuple[str, float]]
    ) -> tuple[str, list[str]]:
        assets = [asset for asset, _ in portfolio]
        candidates = self.base_symbols or [self.getUsdSymbol()]
        best = min(
            candidates,
            key=lambda base: sum(
                asset != base and asset + base not in self.pair_info for asset in assets
            ),
        )
        missing = [
            asset
            for asset in assets
            if asset != best and asset + best not in self.pair_info
        ]
        return best, missing

    def getSupportedPortfolio(
        self, portfolio: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        supported: list[tuple[str, float]] = []
        for asset, amount in portfolio:
            if asset in self.base_symbols or any(
                asset + base in self.pair_info for base in self.base_symbols
            ):
                supported.append((asset, amount))
            else:
                print(
                    (
                        "Warning: {} is not tradeable against a supported "
                        "quote asset"
                    ).format(asset)
                )
        return supported

    def _symbol_filter(self, pair: str, filter_type: str) -> dict[str, str] | None:
        return next(
            (
                item
                for item in self.pair_info[pair]["filters"]
                if item["filterType"] == filter_type
            ),
            None,
        )

    @staticmethod
    def _round_down(value: float, step_size: str) -> str:
        step = Decimal(step_size)
        return format(
            (Decimal(str(value)) / step).to_integral_value(rounding=ROUND_DOWN) * step,
            "f",
        )

    def _minimum_notional(self, pair: str) -> float:
        details = self._symbol_filter(pair, "NOTIONAL") or self._symbol_filter(
            pair, "MIN_NOTIONAL"
        )
        return float(details.get("minNotional", 0)) if details else 0.0

    def _place_order(
        self, symbol: str, base: str, side: str, value: float, live_run: bool
    ) -> float:
        pair = symbol + base
        if pair not in self.pair_info:
            raise ValueError("{} is not a directly tradeable Spot pair".format(pair))
        fee = self._fee(pair)
        value *= 1 - fee
        if value < self._minimum_notional(pair):
            print(
                (
                    "Warning: {} value is below Binance's minimum "
                    "notional; skipping"
                ).format(pair)
            )
            return 0.0

        if not live_run:
            print("DRY RUN: {} {} worth of {}".format(side, value, pair))
            return value

        if side == Client.SIDE_BUY:
            order = self.client.create_order(
                symbol=pair,
                side=side,
                type=Client.ORDER_TYPE_MARKET,
                quoteOrderQty=str(value),
            )
        else:
            lot_size = self._symbol_filter(pair, "MARKET_LOT_SIZE")
            if not lot_size:
                lot_size = self._symbol_filter(pair, "LOT_SIZE")
            if not lot_size:
                raise RuntimeError("{} has no market lot-size filter".format(pair))
            price = Decimal(str(self._pair_price(symbol, base)))
            quantity = self._round_down(
                Decimal(str(value)) / price, lot_size["stepSize"]
            )
            if Decimal(quantity) < Decimal(lot_size["minQty"]):
                print(
                    "Warning: {} quantity is below Binance's minimum; skipping".format(
                        pair
                    )
                )
                return 0.0
            order = self.client.create_order(
                symbol=pair, side=side, type=Client.ORDER_TYPE_MARKET, quantity=quantity
            )

        deadline = time.monotonic() + MAX_ORDER_WAIT_SECONDS
        while order["status"] != "FILLED" and time.monotonic() < deadline:
            time.sleep(ORDER_POLL_SECONDS)
            order = self.client.get_order(symbol=pair, orderId=order["orderId"])
        if order["status"] != "FILLED":
            raise RuntimeError(
                "Market order {} did not fill within {} seconds".format(
                    pair, MAX_ORDER_WAIT_SECONDS
                )
            )
        return float(order.get("cummulativeQuoteQty", value)) * (1 - fee)

    def buyOrder(self, symbol: str, base: str, quant: float, live_run: bool) -> float:
        return self._place_order(symbol, base, Client.SIDE_BUY, quant, live_run)

    def sellOrder(self, symbol: str, base: str, quant: float, live_run: bool) -> float:
        return self._place_order(symbol, base, Client.SIDE_SELL, quant, live_run)
