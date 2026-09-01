"""Portfolio construction and rebalancing logic independent of an exchange SDK."""

from __future__ import annotations

import time
from collections.abc import Sequence


TIMEOUT_BETWEEN_ACTIONS_SECONDS = 30


class IndexFund:
    """Manage a target portfolio through an exchange adapter.

    The adapter values every holding in USD and accepts orders expressed as a
    quote-currency value. ``live_run=False`` uses balances and market data but
    never submits an order.
    """

    def __init__(self, exchange_client) -> None:
        self.exchange = exchange_client
        self._last_action_at: float | None = None

    def _wait_between_actions(self) -> None:
        if self._last_action_at is None:
            return
        remaining = TIMEOUT_BETWEEN_ACTIONS_SECONDS - (
            time.monotonic() - self._last_action_at
        )
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def getTotalWorthPortfolio(portfolio: Sequence[tuple[str, float]]) -> float:
        return sum(value for _, value in portfolio)

    def getTotalWorthUsd(self) -> float:
        return self.getTotalWorthPortfolio(self.getCurrentPortfolio())

    def getCurrentPortfolio(
        self, cached: bool = True, ignore_small_amounts: float = 20
    ) -> list[tuple[str, float]]:
        return self.exchange.getBalanceUsd(
            cached=cached, ignore_small_amounts=ignore_small_amounts
        )

    def _execute_trades(self, trades, trade_func, live_run: bool) -> float:
        self_trades = [trade for trade in trades if trade[0][0] == trade[0][1]]
        market_trades = [trade for trade in trades if trade[0][0] != trade[0][1]]
        available = sum(value for _, value in self_trades)
        available += sum(
            trade_func(asset, base, value, live_run)
            for (asset, base), value in market_trades
        )
        return available

    def _create_trades(self, liquidate_portfolio, invest_portfolio):
        if not liquidate_portfolio and not invest_portfolio:
            return [], []
        base_currency, missing = self.exchange.findBaseCurrency(
            liquidate_portfolio + invest_portfolio
        )
        if missing:
            raise ValueError(
                (
                    "A complete plan cannot use one directly tradeable quote "
                    "currency; unsupported assets: {}"
                ).format(", ".join(missing))
            )
        base_price = self.exchange.getPairPrice(
            base_currency, self.exchange.getUsdSymbol()
        )

        def as_trades(portfolio):
            return [
                ((asset, base_currency), value / base_price)
                for asset, value in portfolio
            ]

        return as_trades(liquidate_portfolio), as_trades(invest_portfolio)

    def _update_portfolio(
        self, target_portfolio, current_portfolio, live_run: bool = False
    ):
        original_target = target_portfolio
        target_portfolio = self.exchange.getSupportedPortfolio(target_portfolio)
        if not target_portfolio:
            raise ValueError(
                "None of the requested target assets are supported by this exchange"
            )
        if target_portfolio != original_target:
            print("Warning: unsupported assets were removed from the target portfolio")
            original_total = self.getTotalWorthPortfolio(original_target)
            supported_total = self.getTotalWorthPortfolio(target_portfolio)
            if supported_total <= 0:
                raise ValueError("Supported target assets have no positive allocation")
            target_portfolio = [
                (asset, value * original_total / supported_total)
                for asset, value in target_portfolio
            ]

        current = dict(current_portfolio)
        target = dict(target_portfolio)
        liquidate_portfolio = [
            (asset, value) for asset, value in current.items() if asset not in target
        ]
        for asset, target_value in target.items():
            difference = target_value - current.get(asset, 0.0)
            if difference < 0:
                liquidate_portfolio.append((asset, -difference))
        invest_portfolio = [
            (asset, target_value - current.get(asset, 0.0))
            for asset, target_value in target.items()
            if target_value > current.get(asset, 0.0)
        ]

        print("#" * 50)
        print("Current portfolio (USD):\n", current_portfolio)
        print("Target portfolio (USD):\n", target_portfolio)
        liquidate_trades, invest_trades = self._create_trades(
            liquidate_portfolio, invest_portfolio
        )
        print("{} trade plan:".format("LIVE" if live_run else "DRY RUN"))
        liquidated_amount = self._execute_trades(
            liquidate_trades, self.exchange.sellOrder, live_run
        )

        required_amount = sum(value for _, value in invest_trades)
        if required_amount:
            scaled_investments = [
                (pair, value * liquidated_amount / required_amount)
                for pair, value in invest_trades
            ]
            self._execute_trades(scaled_investments, self.exchange.buyOrder, live_run)
        else:
            print("No purchases are required.")
        self._last_action_at = time.monotonic()

        updated = (
            target_portfolio if not live_run else self.getCurrentPortfolio(cached=False)
        )
        if live_run:
            target_assets = set(target)
            updated = [item for item in updated if item[0] in target_assets]
        print("Updated portfolio (USD):\n", updated)
        print("#" * 50)
        return updated

    def _source_portfolio(self, source_currencies, source_amount):
        current = self.getCurrentPortfolio()
        if not source_currencies:
            return current
        current_by_asset = dict(current)
        if source_amount and len(source_amount) != len(source_currencies):
            raise ValueError("source_amount and source_currencies length mismatch")
        if not source_amount:
            return [
                (asset, current_by_asset[asset])
                for asset in source_currencies
                if asset in current_by_asset
            ]
        selected = list(zip(source_currencies, source_amount))
        for asset, amount in selected:
            if current_by_asset.get(asset, 0.0) < amount:
                raise ValueError(
                    "Requested source amount for {} exceeds the wallet balance".format(
                        asset
                    )
                )
        return selected

    def rebalance(
        self,
        portfolio=None,
        source_currencies=None,
        source_amount=None,
        not_invest_list=None,
        do_not_alter=None,
        weight=None,
        live_run: bool = False,
    ):
        if not portfolio:
            portfolio = source_currencies or [
                asset for asset, _ in self.getCurrentPortfolio()
            ]
        return self.reinvest(
            portfolio,
            source_currencies,
            source_amount,
            not_invest_list,
            do_not_alter,
            weight,
            live_run,
        )

    def reinvest(
        self,
        portfolio,
        source_currencies=None,
        source_amount=None,
        not_invest_list=None,
        do_not_alter=None,
        weight=None,
        live_run: bool = False,
    ):
        self._wait_between_actions()
        if not portfolio:
            raise ValueError("A target portfolio is required")
        source_currencies = source_currencies or []
        source_amount = source_amount or []
        blocked = set(not_invest_list or []) | set(do_not_alter or [])
        current_portfolio = [
            item
            for item in self._source_portfolio(source_currencies, source_amount)
            if item[0] not in blocked
        ]
        total_value = self.getTotalWorthPortfolio(current_portfolio)
        if not current_portfolio or total_value <= 0:
            print("Portfolio to reinvest from is empty")
            return None

        assets = [item if isinstance(item, str) else item[0] for item in portfolio]
        assets = [asset for asset in assets if asset not in blocked]
        if not assets:
            print("Nothing to invest in given the constraints")
            return None
        if weight is None:
            weight = [1.0] * len(assets)
        if len(weight) != len(assets):
            raise ValueError("Length of weights and portfolio is not equal")
        weight_total = sum(weight)
        if weight_total <= 0:
            raise ValueError("Portfolio weights must sum to a positive value")
        target = [
            (asset, total_value * item_weight / weight_total)
            for asset, item_weight in zip(assets, weight)
        ]
        return self._update_portfolio(target, current_portfolio, live_run)

    def liquidate(
        self,
        portfolio=None,
        do_not_alter=None,
        not_invest_list=None,
        live_run: bool = False,
    ):
        self._wait_between_actions()
        chosen = set(portfolio or [])
        blocked = set(do_not_alter or [])
        current = [
            item
            for item in self.getCurrentPortfolio()
            if (not chosen or item[0] in chosen) and item[0] not in blocked
        ]
        total_value = self.getTotalWorthPortfolio(current)
        if not current or total_value <= 0:
            print("Portfolio to liquidate is already empty")
            return None
        base_currency, _ = self.exchange.findBaseCurrency(current)
        if base_currency in set(not_invest_list or []):
            raise ValueError("The selected liquidation currency is in not_invest_list")
        return self._update_portfolio([(base_currency, total_value)], current, live_run)
