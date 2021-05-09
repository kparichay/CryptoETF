#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   execute_index_fund.py
# @date   24 April 2021
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Execute the actions for index fund

import argparse
import os
import configparser

from binance_client import BinanceClient
from index_fund import IndexFund
from coinmarketcap_client import CoinMarketCapClient

DEBUG=True

def getKeys(keys_file, exchange):
    # parse keys
    if not os.path.isfile(keys_file):
        raise BaseException("Provided keys file does not exist")

    config = configparser.ConfigParser()
    config.read(keys_file)

    keys = {}
    # Get keys for the given exchange
    if exchange in config:
        for key in config[exchange]:
            keys[key] = config[exchange][key]

    return keys


def main(args):
    bnb_keys = getKeys(args.keys, "binance")
    fund = IndexFund(
        BinanceClient(api_key=bnb_keys["api_key"],
                      secret_key=bnb_keys["secret_key"])
    )

    cmc_keys = getKeys(args.keys, "coinmarketcap")
    if 'api_key' in cmc_keys and len(cmc_keys['api_key']) > 0:
        cmc = CoinMarketCapClient(cmc_keys["api_key"])
    else:
        print('Warn: CoinMarketCap key not provided. ' \
            'Default portfolios (Large, Mid, Small) will not be supported.')
        cmc = None

    def realizePortfolio(portfolio, amounts=None):
        amount_set = False
        if amounts != None:
            amount_set = len(portfolio) == len(amounts)

        currencies = []
        updated_amounts = []
        for idx, pf in enumerate(portfolio):
            if cmc and hasattr(cmc, "get" + pf.title() + "Cap"):
                new_portfolio = cmc.__getattribute__("get" + pf.title() + "Cap")()
                currencies += new_portfolio
                if amount_set:
                    new_amount = [amounts[idx] / len(new_portfolio)] * len(new_portfolio)
                    updated_amounts += new_amount
            else:
                currencies.append(pf)
                if amount_set:
                    updated_amounts.append(amounts[idx])

        if amounts != None:
            return currencies, updated_amounts
        
        return currencies, None

    # Create arguments for the functions based on the passed args
    kwargs = {}
    kwargs["live_run"] = args.live

    kwargs['portfolio'] = None
    if args.portfolio:
        kwargs['portfolio'], _ = realizePortfolio(args.portfolio)
        if len(kwargs['portfolio']) == 0 and len(args.portfolio) > 0:
            raise BaseException('Provided portfolio not supported with the given information'
            'Considering providing other portfolios or giving exchange keys, if any')
        if len(args.portfolio) < len(kwargs['portfolio']):
            print('Some of the unsupported coins in portfolio have been removed.')
            print('Target portfolio - ', kwargs['portfolio'])
            input("Press any key to continue:")

    if args.weight:
        kwargs["weight"] = args.weight

    if args.source_portfolio:
        kwargs["source_currencies"], kwargs["source_amount"] = realizePortfolio(args.source_portfolio, args.source_amount)
        if kwargs['source_amount'] == None or len(kwargs['source_amount']) == 0:
            del kwargs["source_amount"]
        if 'source_amount' in kwargs and len(kwargs['source_currencies']) != len(kwargs['source_amount']):
            raise BaseException('source_amount and source_currencies length mismatch')

    # TODO: if rebalance done less than some days ago, then dont rebalance again
    if args.update_min_freq:
        raise BaseException("Update minimum frequency is not yet enabled")

    kwargs["do_not_alter"], _ = realizePortfolio(args.do_not_alter)
    kwargs["not_invest_list"], _ = realizePortfolio(args.not_invest_list)

    if DEBUG:
        print(args) 

    if args.liquidate:
        fund.liquidate(**kwargs)
    elif args.reinvest:
        fund.reinvest(**kwargs)
    elif args.rebalance:
        fund.rebalance(**kwargs)
    elif args.leverage_bull:
        fund.leverage(mode='bull', **kwargs)
    elif args.leverage_bear:
        fund.leverage(mode='bear', **kwargs)
    elif args.leverage_liquidate:
        fund.leverage(mode='liquidate', **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index Fund Manager")
    # Primary action to the portfolio
    # title='Primary Action', description='Choose one of the below primary action',
    exclusive_group = parser.add_mutually_exclusive_group(required=True)
    exclusive_group.add_argument(
        "--liquidate",
        action="store_true",
        default=False,
        help="Liquidate the portfoilio.",
    )
    exclusive_group.add_argument(
        "--reinvest", action="store_true", default=False, help="Reinvest from source to target portfolio."
    )
    exclusive_group.add_argument(
        "--rebalance",
        action="store_true",
        default=False,
        help="Rebalance the portfoilio.",
    )
    exclusive_group.add_argument(
        "--leverage_bull",
        action="store_true",
        default=False,
        help="Convert the portfolio to its leveraged bull coins where ever possible.",
    )
    exclusive_group.add_argument(
        "--leverage_bear",
        action="store_true",
        default=False,
        help="Convert the portfolio to its leveraged bear coins where ever possible.",
    )
    exclusive_group.add_argument(
        "--leverage_liquidate",
        action="store_true",
        default=False,
        help="Liquidate the leverage position, and convert the portfolio to its non-leveraged coins.",
    )

    # Arguments for the regular users
    basic_group = parser.add_argument_group(
        title="Basic Arguments", description="for regular users."
    )
    basic_group.add_argument(
        "--keys",
        type=str,
        default="keys",
        help="File containing the keys of the accounts. \
                                 Check keys.sample to create one for yourself.",
    )
    basic_group.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Do a live-run where real trades takes place.",
    )
    basic_group.add_argument(
        "--portfolio",
        nargs="+",
        choices=["small", "mid", "large"],
        help="Choose the prebuilt portfolios to invest in."
        "Large is top 20, medium is next 30, and small is next 100."
        "This also support directly specifying currencies as well.",
    )
    basic_group.add_argument(
        "--weight",
        nargs="+",
        type=float,
        help="Weightage for the investments. Given weights will be normalized. \
        Defaults to equal weightage.",
    )
    basic_group.add_argument(
        "--source_amount",
        nargs="+",
        type=float,
        help="Source amounts to be used for source currencies/portfolio for investing to fund/portfolio in terms of USD. "
        "Ignored for liquidation.",
    )
    basic_group.add_argument(
        "--source_portfolio",
        nargs="+",
        type=str,
        help="source currencies/portfolio from where to invest from. Ignore for liquidation.",
    )
    basic_group.add_argument(
        "--update_min_freq",
        type=int,
        help="number of hours to wait before the previous rebalance or reinvest. This aragument is ignored for liquidate.",
    )

    # Arguments for the professional users
    pro_group = parser.add_argument_group(
        title="Pro Arguments",
        description="Only for professional users. \
            Pro arguments override regular arguments.",
    )
    pro_group.add_argument(
        "--do_not_alter",
        nargs="+",
        type=str,
        default=[],
        help="Investment in these currencies shall not be altered.",
    )
    pro_group.add_argument(
        "--not_invest_list",
        nargs="+",
        type=str,
        default=[],
        help="Investment in these currencies shall not be done. \
        Already invested amount will be redeemed.",
    )

    # TODO: Arguments for running this as a background script
    bg_group = parser.add_argument_group(
        title="Background script Arguments",
        description="for running this in background.",
    )
    bg_group.add_argument(
        "--cron",
        action="store_true",
        default=False,
        help="The given configuration will run as a cron job",
    )
    bg_group.add_argument(
        "--freq", type=int, default=24, help="The given configuration will run at this frequency in hours."
    )
    bg_group.add_argument(
        "--email", type=str, help="Sends logs on email upon running."
    )
    
    args = parser.parse_args()

    if args.live:
        print("Warn: This is a live run and real trades will take place. ")
        input("Press any key to continue:")
    else:
        print("Warn: This is a dry run and no real trades will take place. "
        "Use --live to make actual trades.")

    try:
        main(args)
    except BaseException as e:
        print('Error:', e, '!!!')
        if DEBUG:
            raise e
