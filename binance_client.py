#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   binance_client.py
# @date   24 April 2021
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Client for the Binance exchange

import time
from collections import defaultdict
from decimal import Decimal, ROUND_DOWN

from binance.client import Client

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
            print("Error: System status is {}, exiting...".format(
                self.system_status["msg"]))
            raise BaseException("System status is {}".format(
                self.system_status["msg"]))

        self.account_status = self.client.get_account_status()
        if (self.account_status["success"] != True
                or self.account_status["msg"] != "Normal"):
            print(
                "Error: Account status is not normal or could not be retreived, exiting..."
            )
            raise BaseException("Account status is not normal")

        self.info = self.client.get_account()
        self.all_pairs = dict([(x["symbol"], float(x["price"]))
                               for x in self.client.get_all_tickers()])
        self.all_pairs_info = self.client.get_exchange_info()
        self.__updateBalance()

        base_symbols_count = defaultdict(int)
        for sym in self.all_symbols:
            for pair in self.all_pairs:
                if pair.endswith(sym):
                    base_symbols_count[sym] += 1

        self.base_symbols = sorted(base_symbols_count.items(), key=lambda x: x[1], reverse=True)
        # base symbols are sorted by the number of pairs they form
        self.base_symbols = [x[0] for x in self.base_symbols]
        # top 5 are sufficient, lower ones can also work but might have low volume
        # and this will result in higher spread leading to heavy cost of market transaction
        self.base_symbols = self.base_symbols[:5]

    def __updateBalance(self, cached=True):
        if hasattr(self, "balance") and cached:
            return

        self.full_balance = self.info["balances"]
        self.all_symbols = [x["asset"] for x in self.full_balance]
        # balance must be more than 0
        self.balance = list(
            filter(
                lambda x: float(x["free"]) > 0,
                self.full_balance,
            ))
        # all symbols in balance must be tradeable
        self.balance = list(filter(lambda x: len([y for y in self.all_pairs if y.startswith(x['asset'])]) > 0, self.balance))

    def __getNumPairsWithBaseCurrencies(self):
        for base in self.base_symbols:
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

    def __getPriceWrt(self, symbol, base):
        if base not in self.base_symbols:
            raise BaseException("base currency not found")
        if symbol not in self.all_symbols:
            raise BaseException("symbol not found")

        price_wrt_base = None
        price_base = None
        for base_cur in [base] + self.base_symbols:
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

    def getPairPrice(self, symbol, base):
        if symbol == base:
            return 1.
        else:
            return self.__getPriceWrt(symbol, base)

    def getUsdSymbol(self):
        return 'USDT'

    def getBalanceUsd(self, cached=True, ignore_small_amounts=20):
        self.__updateBalance(cached=cached)
        balance_usd = self.getPortfolioUsd([(b['asset'], b['free']) for b in self.balance])

        self.balance_usd = sorted(balance_usd,
                                  key=lambda x: x[1],
                                  reverse=True)
        self.balance_usd = list(
            filter(lambda x: x[1] > ignore_small_amounts, self.balance_usd))
        return self.balance_usd

    def getPortfolioUsd(self, portfolio):
        portfolio = [(x[0], float(x[1]) * self.__getPriceWrt(x[0], base=self.getUsdSymbol())) for x in portfolio]
        return portfolio

    def __getPairLotInfo(self, pair, key, filter_type):
        pair_info = list(filter(lambda x : x['symbol'] == pair, self.all_pairs_info['symbols']))[0]
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
        pair_str = symbol + '/' + base
        if pair not in self.all_pairs:
            raise BaseException('Pair to trade is not available on the exchange')

        # reduce the quant by fee to avoid not enough balance issues
        quant *= 1 - FEE

        # if quant is below minimum tradeable quantity, then simply return
        if quant < self.__getMinNotional(pair):
            print(
                "Warn: Quantity less than minimum notional quantity, skipping...")
            return 0.0

        # Convert quant from base to target
        base_quant = quant
        price = self.__getPriceWrt(symbol, base=base)
        quant = quant / price

        # if quant is below minimum tradeable quantity, then simply return
        if quant < self.__getMinQuantity(pair):
            print(
                "Warn: Quantity less than minimum tradeable quantity, skipping...")
            return 0.0

        # ensure that quantity follow stepsize granularity
        step_size = str(self.__getStepSize(pair))
        quant = str(
            Decimal(quant).quantize(Decimal(step_size), rounding=ROUND_DOWN))
        base_quant = str(
            Decimal(base_quant).quantize(Decimal(step_size), rounding=ROUND_DOWN))

        print(" pair = {}, side = {}, base quant = {}, quant = {}".format(
            pair_str, side, base_quant, quant))

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
        portfolio = [x[0] for x in portfolio]
        min_num_missing_currencies = len(portfolio)
        best_base_currency = None

        for base_currency in self.base_symbols:
            num_missing_currencies = len(list(filter(
                            lambda x: x + base_currency not in self.
                            all_pairs and x != base_currency,
                            portfolio)))

            if num_missing_currencies < min_num_missing_currencies:
                min_num_missing_currencies = num_missing_currencies
                best_base_currency = base_currency

        missing_currencies = list(filter(
                            lambda x: x + best_base_currency not in self.
                            all_pairs and x != best_base_currency,
                            portfolio))
        
        return best_base_currency, missing_currencies

    def getSupportedPortfolio(self, portfolio):
        supported_portfolio = []
        for symbol, amount in portfolio:
            found = False
            for base_currency in self.base_symbols:
                if symbol + base_currency in self.all_pairs:
                    found = True
                    break
            if found:
                supported_portfolio.append((symbol, amount))
            else:
                print('Warn: Symbol ', symbol, ' not supported by the exchange')

        return supported_portfolio

    def __getLeveragedCurrencies(self, direction):
        return [x.split(direction)[0] for x in self.all_pairs if direction in x and ''.join(x.split(direction)) in self.all_pairs]

    def getLeveragedCurrencies(self):
        if hasattr(self, 'all_leveraged_symbols'):
            return self.all_leveraged_symbols

        ups = self.__getLeveragedCurrencies('UP')
        downs = self.__getLeveragedCurrencies('DOWN')
        self.all_leveraged_symbols = list(set(ups) & set(downs))

        return self.all_leveraged_symbols

    def __getLeveragedSymbol(self, symbol, side):
        if symbol not in self.all_symbols:
            raise BaseException('Given symbol ', symbol, ' not supported')

        if symbol not in self.getLeveragedCurrencies():
            raise BaseException('Given symbol ', symbol, ' cannot be leveraged.')

        return symbol + side
        
    def getBullSymbol(self, symbol):
        return self.__getLeveragedSymbol(symbol, side='UP')

    def getBearSymbol(self, symbol):
        return self.__getLeveragedSymbol(symbol, side='DOWN')