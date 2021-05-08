#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   binance_client.py
# @date   24 April 2021
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Client for the Binance exchange

from binance.client import Client
import time
from decimal import Decimal, ROUND_DOWN

base_currencies = ["USDT", "BTC", "BNB"]  # base currencies with the most pairs
blacklist_currencies = [
    "EON",
    "ADD",
    "MEETONE",
    "ATD",
    "EOP",
    "CBM",
]  # binance does not give their price

MAX_TRY_TILL_FAIL = 120  # sec
MAX_WAIT_BW_TRIES = 10  # sec

FEE = 0.1 * 0.01  # fee in fraction


def getTimeSec():
    return round(time.time() * 1000 * 1000)


class BinanceClient:
    """
    Client for Binance exchange
    TODO: add support for marginal account
    FIXME: this returns a very delayed balance. use WS with Payload: Account Update
    """

    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)
        self.system_status = self.client.get_system_status()
        if self.system_status["status"] != 0:
            print("System status is {}, exiting...".format(
                self.system_status["msg"]))
            raise BaseException("System status is {}".format(
                self.system_status["msg"]))

        self.account_status = self.client.get_account_status()
        if (self.account_status["success"] != True
                or self.account_status["msg"] != "Normal"):
            print(
                "Account status is not normal or could not be retreived, exiting..."
            )
            raise BaseException("Account status is not normal")

        self.info = self.client.get_account()
        self.all_pairs = dict([(x["symbol"], float(x["price"]))
                               for x in self.client.get_all_tickers()])

    def __updateBalance(self):
        self.full_balance = self.info["balances"]
        self.all_symbols = [x["asset"] for x in self.full_balance]
        self.def_balance = list(
            filter(
                lambda x: float(x["free"]) > 0 and x["asset"] not in
                blacklist_currencies,
                self.full_balance,
            ))

    def __getNumPairsWithBaseCurrencies(self):
        for base in base_currencies:
            print(
                "base = ",
                base,
                ", num of pairs = ",
                len(
                    list(
                        filter(lambda x: x.endswith(base),
                               self.all_pairs.keys()))),
            )

    def __getPairPrice(self, sym1, sym2):
        pair = sym1 + sym2
        pair_ = sym2 + sym1
        if pair in self.all_pairs:
            return self.all_pairs[pair]
        elif pair_ in self.all_pairs:
            return 1.0 / self.all_pairs[pair_]

        raise BaseException("pair not found")

    def __getPriceWrt(self, symbol, base="USDT"):
        if base not in base_currencies:
            raise BaseException("base currency not found")
        if symbol not in self.all_symbols:
            raise BaseException("symbol not found")

        price_wrt_base = None
        price_base = None
        for base_cur in [base] + base_currencies:
            try:
                price_wrt_base = self.__getPairPrice(symbol, base_cur)
                price_base = base_cur
                break
            except:
                pass

        if base == price_base:
            return price_wrt_base
        else:
            return price_wrt_base * self.__getPairPrice(price_base, base)

    def getBalanceUsd(self, cached=True, ignore_small_amounts=20):
        if hasattr(self, "balance_usd") and cached:
            return self.balance_usd

        self.__updateBalance()
        balance_usd = self.getPortfolioUsd([(b['asset'], b['free']) for b in self.def_balance])

        self.balance_usd = sorted(balance_usd,
                                  key=lambda x: x[1],
                                  reverse=True)
        self.balance_usd = list(
            filter(lambda x: x[1] > ignore_small_amounts, self.balance_usd))
        return self.balance_usd

    def getPortfolioUsd(self, portfolio):
        portfolio = [(x[0], float(x[1]) * self.__getPriceWrt(x[0], base="USDT")) for x in portfolio]
        return portfolio

    def __getPairLotInfo(self, pair, key, filter_type):
        pair_info = self.client.get_symbol_info(pair)
        min_info = list(
            filter(lambda x: x["filterType"] == filter_type,
                   pair_info["filters"]))
        assert len(min_info) == 1
        return min_info[0][key]

    def __getMinNotional(self, pair):
        return float(self.__getPairLotInfo(pair, "minNotional",
                                           "MIN_NOTIONAL"))

    def __getMinQuantity(self, pair):
        return float(self.__getPairLotInfo(pair, "minQty", "LOT_SIZE"))

    def __getStepSize(self, pair):
        return float(self.__getPairLotInfo(pair, "stepSize", "LOT_SIZE"))

    def __placeOrder(self, symbol, base, side, quant, live_run):
        pair = symbol + base
        if pair not in self.all_pairs:
            raise BaseException('Pair to trade is not available on the exchange')

        # reduce the quant by fee to avoid not enough balance issues
        quant *= 1 - FEE

        # if quant is below minimum tradeable quantity, then simply return
        if quant < self.__getMinNotional(pair):
            print(
                "  Quantity less than minimum notional quantity, skipping...")
            return 0.0

        # Convert quant from base to target
        base_quant = quant
        price = self.__getPriceWrt(symbol, base=base)
        quant = quant / price

        # if quant is below minimum tradeable quantity, then simply return
        if quant < self.__getMinQuantity(pair):
            print(
                "  Quantity less than minimum tradeable quantity, skipping...")
            return 0.0

        # ensure that quantity follow stepsize granularity
        step_size = str(self.__getStepSize(pair))
        quant = str(
            Decimal(quant).quantize(Decimal(step_size), rounding=ROUND_DOWN))
        base_quant = str(
            Decimal(base_quant).quantize(Decimal(step_size), rounding=ROUND_DOWN))

        print(" pair = {}, side = {}, base quant = {}, quant = {}".format(
            pair, side, base_quant, quant))

        if live_run:
            order = self.client.create_order(symbol=pair,
                                            side=side,
                                            type=Client.ORDER_TYPE_MARKET,
                                            quantity=quant)

            if order == None:
                raise BaseException("Placing the order failed")

            start_time = getTimeSec()
            while (order["status"] != "FILLED"
                and getTimeSec() <= MAX_TRY_TILL_FAIL + start_time):
                time.sleep(MAX_WAIT_BW_TRIES)
                order = self.client.get_order(symbol=pair,
                                            orderId=order["orderId"])

            if order["status"] != "FILLED":
                raise BaseException("Order did not fill itself")

            traded_quant = 0
            for fill in order["fills"]:
                traded_quant += float(fill["price"]) * float(
                    fill["qty"]) * (1 - FEE)

            return traded_quant
        else:
            return 0

    def buyOrder(self, symbol, base, quant, live_run):
        return self.__placeOrder(symbol,
                                 base,
                                 side=Client.SIDE_BUY,
                                 quant=quant, 
                                 live_run=live_run)

    def sellOrder(self, symbol, base, quant, live_run):
        return self.__placeOrder(symbol,
                                 base,
                                 side=Client.SIDE_SELL,
                                 quant=quant,
                                 live_run=live_run)

    def findBaseCurrency(self, portfolio):
        for base_currency in base_currencies:
            print(list(
                        filter(
                            lambda x: x[0] + base_currency not in self.
                            all_pairs and x[0] != base_currency,
                            portfolio,
                        )))
            if (len(
                    list(
                        filter(
                            lambda x: x[0] + base_currency not in self.
                            all_pairs and x[0] != base_currency,
                            portfolio,
                        ))) == 0):
                return base_currency

        raise BaseException("Cant find base currency for the portfolio")
