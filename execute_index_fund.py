#!/usr/bin/env python3
"""Command-line entry point for a self-managed crypto index fund."""

from __future__ import annotations

import argparse
import configparser
from pathlib import Path
from typing import Sequence

from binance_client import BinanceClient
from coinmarketcap_client import CoinMarketCapClient
from index_fund import IndexFund


def get_keys(keys_file: str, exchange: str) -> dict[str, str]:
    path = Path(keys_file)
    if not path.is_file():
        raise FileNotFoundError("Keys file does not exist: {}".format(path))
    config = configparser.ConfigParser()
    config.read(path)
    return dict(config[exchange]) if exchange in config else {}


def _realize_portfolio(portfolio, amounts, cmc):
    if amounts is not None and len(portfolio or []) != len(amounts):
        raise ValueError(
            "--source-amount must provide one value per --source-portfolio entry"
        )
    currencies: list[str] = []
    realized_amounts: list[float] = []
    amount_set = amounts is not None
    for index, entry in enumerate(portfolio or []):
        selector_name = "get{}Cap".format(entry.title())
        is_selector = entry.lower() in {"large", "mid", "small"}
        if is_selector and cmc is None:
            raise ValueError("{} requires a [coinmarketcap] api_key".format(entry))
        selector = getattr(cmc, selector_name, None) if cmc else None
        selected = selector() if selector else [entry]
        currencies.extend(selected)
        if amount_set:
            realized_amounts.extend([amounts[index] / len(selected)] * len(selected))
    return currencies, realized_amounts if amount_set else None


def run(args: argparse.Namespace):
    if args.live and not args.yes:
        raise ValueError(
            "Live trading requires --yes. Use --testnet first whenever possible."
        )
    print(
        "LIVE RUN: real orders may be submitted."
        if args.live
        else "DRY RUN: no orders will be submitted."
    )

    binance_keys = get_keys(args.keys, "binance")
    fund = IndexFund(
        BinanceClient(
            api_key=binance_keys.get("api_key", ""),
            secret_key=binance_keys.get("secret_key", ""),
            tld=args.tld,
            testnet=args.testnet,
        )
    )

    cmc_keys = get_keys(args.keys, "coinmarketcap")
    cmc = CoinMarketCapClient(cmc_keys["api_key"]) if cmc_keys.get("api_key") else None

    kwargs = {"live_run": args.live}
    kwargs["portfolio"], _ = _realize_portfolio(args.portfolio, None, cmc)
    if args.weight:
        kwargs["weight"] = args.weight
    if args.source_portfolio:
        source, amounts = _realize_portfolio(
            args.source_portfolio, args.source_amount, cmc
        )
        kwargs["source_currencies"] = source
        if amounts:
            kwargs["source_amount"] = amounts
    elif args.source_amount:
        raise ValueError("--source-amount requires --source-portfolio")
    kwargs["do_not_alter"], _ = _realize_portfolio(args.do_not_alter, None, cmc)
    kwargs["not_invest_list"], _ = _realize_portfolio(args.not_invest_list, None, cmc)

    if args.liquidate:
        return fund.liquidate(
            portfolio=kwargs["portfolio"],
            do_not_alter=kwargs["do_not_alter"],
            not_invest_list=kwargs["not_invest_list"],
            live_run=args.live,
        )
    if args.reinvest:
        if not kwargs["portfolio"]:
            raise ValueError("--reinvest requires --portfolio")
        return fund.reinvest(**kwargs)
    return fund.rebalance(**kwargs)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and rebalance a Binance Spot crypto index fund."
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--liquidate",
        action="store_true",
        help="Sell the selected holdings into a common quote asset.",
    )
    actions.add_argument(
        "--reinvest",
        action="store_true",
        help="Move selected holdings into the target portfolio.",
    )
    actions.add_argument(
        "--rebalance",
        action="store_true",
        help="Rebalance selected holdings to the target weights.",
    )
    parser.add_argument(
        "--keys", default="keys", help="INI credentials file; see keys.sample."
    )
    parser.add_argument(
        "--tld", default="com", help="Binance domain suffix, for example 'us'."
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use Binance Spot Testnet credentials and endpoint.",
    )
    parser.add_argument(
        "--live", action="store_true", help="Submit real orders; requires --yes."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Acknowledge that --live can submit orders."
    )
    parser.add_argument(
        "--portfolio",
        nargs="+",
        help="Assets or built-in selectors: Large, Mid, Small.",
    )
    parser.add_argument(
        "--weight", nargs="+", type=float, help="Target weights, normalized to 1."
    )
    parser.add_argument(
        "--source-portfolio",
        nargs="+",
        help="Assets/selectors to fund the operation from.",
    )
    parser.add_argument(
        "--source-amount",
        nargs="+",
        type=float,
        help="USD amount for each source entry.",
    )
    parser.add_argument(
        "--do-not-alter", nargs="+", default=[], help="Assets that must not be traded."
    )
    parser.add_argument(
        "--not-invest-list",
        nargs="+",
        default=[],
        help="Assets excluded from the target.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None):
    return run(parse_args(argv))


if __name__ == "__main__":
    main()
