#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   index_fund.py
# @date   24 April 2021
# @see
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Manage the index fund and its API

import time

# This allows timeout for balance to update as many exchanges take time for latest balance to update
TIMEOUT_BW_CALLS = 30  # sec


def getTimeSec():
    return round(time.time() * 1000 * 1000)


class IndexFund:
    """
    Index Fund to manage and execute a given portfolio
    TODO: add support for multiple base currencies
    """

    def __init__(self, exchange_client):
        self.exchange = exchange_client
        self.last_time = 0

    def __waitTimeout(self):
        while getTimeSec() - self.last_time < TIMEOUT_BW_CALLS:
            time.sleep(1)

    def getTotalWorthPortfolio(self, portfolio):
        return sum(map(lambda x: x[1], portfolio))

    def getTotalWorthUsd(self):
        return self.getTotalWorthPortfolio(self.getCurrentPortfolio())

    def getCurrentPortfolio(self, cached=True, ignore_small_amounts=20):
        return self.exchange.getBalanceUsd(
            cached=cached, ignore_small_amounts=ignore_small_amounts)

    def __tradePortfolio(self, portfolio, base_currency, tradeFunc, live_run):
        return sum([
            tradeFunc(symbol, base_currency, quant, live_run)
            for symbol, quant in portfolio
        ])

    def __liquidatePortfolio(self, portfolio, base_currency, live_run):
        return self.__tradePortfolio(portfolio, base_currency,
                                     self.exchange.sellOrder, live_run)

    def __investPortfolio(self, portfolio, base_currency, live_run):
        return self.__tradePortfolio(portfolio, base_currency,
                                     self.exchange.buyOrder, live_run)

    def __updatePortfolio(self,
                          target_portfolio,
                          current_portfolio,
                          live_run=False):

        # Update the portfolio
        print("##################################################")
        print("Current Portfolio -> \n", current_portfolio)
        print("##################################################")
        print("Target Portfolio -> \n", target_portfolio)
        print("##################################################")

        current_symbols = [x[0] for x in current_portfolio]
        target_symbols = [x[0] for x in target_portfolio]

        # if target not in current, add dummy
        current_portfolio += [(x[0], 0.0) for x in filter(
            lambda x: x[0] not in current_symbols, target_portfolio)]

        # if current not in target, liquidate
        liquidate_portfolio = list(
            filter(lambda x: x[0] not in target_symbols, current_portfolio))

        # remove liquidated currencies from current
        current_portfolio = [
            x for x in current_portfolio if x not in liquidate_portfolio
        ]

        target_portfolio = sorted(target_portfolio, key=lambda x: x[0])
        current_portfolio = sorted(current_portfolio, key=lambda x: x[0])

        # get diff portfolio
        diff_portfolio = [
            (target[0], target[1] - current[1])
            for target, current in zip(target_portfolio, current_portfolio)
        ]

        # filter portfolio to be liquidated or to be invested
        liquidate_portfolio += [
            (x[0], -x[1])
            for x in list(filter(lambda x: x[1] < 0, diff_portfolio))
        ]
        invest_portfolio = list(filter(lambda x: x[1] > 0, diff_portfolio))

        # execute the trades
        base_currency = self.exchange.findBaseCurrency(liquidate_portfolio +
                                                       invest_portfolio)

        # filter out trades of base_currency itself
        base_current_trades = list(
            filter(lambda x: x[0] == base_currency, liquidate_portfolio))
        liquid_base_currency_amount = 0.0
        if len(base_current_trades) > 0:
            liquid_base_currency_amount += list(
                filter(lambda x: x[0] == base_currency,
                       liquidate_portfolio))[0][1]

        liquidate_portfolio = list(
            filter(lambda x: x[0] != base_currency, liquidate_portfolio))
        invest_portfolio = list(
            filter(lambda x: x[0] != base_currency, invest_portfolio))

        if live_run:
            print("Executing Trades (LIVE) -> ")
        else:
            print("Executing Trades (NOT LIVE) -> ")

        liquidated_amount = self.__liquidatePortfolio(
            liquidate_portfolio, base_currency, live_run)
        liquidated_amount += liquid_base_currency_amount

        # scale down the invest portfolio by the amount which has been aggregated by the sales
        amount_required = sum([x[1] for x in invest_portfolio])
        invest_portfolio = [(x[0],
                                x[1] / amount_required * liquidated_amount)
                            for x in invest_portfolio]

        self.__investPortfolio(invest_portfolio, base_currency, live_run)
        print("##################################################")

        if not live_run:
            return target_portfolio

        # Return the updated portfolio
        return self.getCurrentPortfolio(cached=False)

    def rebalance(
        self,
        portfolio,
        source_currencies=[],
        source_amount=[],
        not_invest_list=[],
        do_not_alter=[],
        weight=None,
        live_run=False,
    ):
        # if portfolio not provided, use full current portfolio
        if portfolio is None or len(portfolio) == 0:
            if len(source_currencies) != 0:
                portfolio = source_currencies
                if len(source_amount) == len(source_currencies):
                    portfolio = self.exchange.getPortfolioUsd(list(zip(source_currencies, source_amount)))
            else:
                portfolio = self.getCurrentPortfolio()

        return self.reinvest(
            portfolio=portfolio,
            source_currencies=source_currencies,
            source_amount=source_amount,
            not_invest_list=not_invest_list,
            do_not_alter=do_not_alter,
            weight=weight,
            live_run=live_run,
        )

    def reinvest(
        self,
        portfolio,
        source_currencies=[],
        source_amount=[],
        not_invest_list=[],
        do_not_alter=[],
        weight=None,
        live_run=False,
    ):
        self.__waitTimeout()

        # if portfolio not provided, error
        if portfolio is None or len(portfolio) == 0:
            raise BaseException("New portfolio not provided.")

        current_portfolio = self.getCurrentPortfolio()

        # intersect with source_currencies
        if len(source_currencies) > 0:
            current_portfolio = list(
                filter(lambda x: x[0] in source_currencies, current_portfolio))
            if len(source_currencies) == len(source_amount):
                source_portfolio = self.exchange.getPortfolioUsd(list(zip(source_currencies, source_amount)))
                for bc, ba in source_portfolio:
                    if len(list(filter(lambda x: x[0] == bc and x[1] > ba, current_portfolio))) != 1:
                        raise BaseException(
                            "Given base amount exceeds the amount in wallet")
                    
                current_portfolio = source_portfolio

        # remove currencies which are in do_not_alter lists
        current_portfolio = list(
            filter(lambda x: x[0] not in do_not_alter, current_portfolio))

        # total of the portfolio to be updated
        total_value = self.getTotalWorthPortfolio(current_portfolio)

        # Nothing to do if current portfolio is empty
        if len(current_portfolio) == 0 or total_value == 0.0:
            print("Portfolio to reinvest from is empty")
            return

        # allow portfolio to be just list of currencies or currency, value pair
        if not isinstance(portfolio[0], str):
            portfolio = [x[0] for x in portfolio]

        # filter out currencies from ignore list
        portfolio = list(filter(lambda x: x not in not_invest_list, portfolio))
        # filter out currencies from do not alter list
        portfolio = list(filter(lambda x: x not in do_not_alter, portfolio))

        # Nothing to do if portfolio is empty
        if len(portfolio) == 0:
            print("Nothing to invest to given the current constraints")
            return

        # if weights not provided, set them all equal and normalize them
        if weight is None:
            weight = [1] * len(portfolio)
        weight = [x / sum(weight) for x in weight]

        # created weighted portfolio
        if len(weight) != len(portfolio):
            raise BaseException('Length of weights and portfolio is not equal')
        portfolio = [(x, total_value * w) for x, w in zip(portfolio, weight)]

        # update the portfolio
        return self.__updatePortfolio(
            target_portfolio=portfolio,
            current_portfolio=current_portfolio,
            live_run=live_run
        )


    def liquidate(self,
                  portfolio=[],
                  do_not_alter=[],
                  not_invest_list=[],
                  live_run=False
    ):
        self.__waitTimeout()

        current_portfolio = self.getCurrentPortfolio()
        if len(portfolio) == 0:
            current_portfolio = current_portfolio
        else:
            current_portfolio = list(
                filter(lambda x: x[0] in portfolio, current_portfolio))

        # remove currencies which are in do_not_alter lists
        current_portfolio = list(
            filter(lambda x: x[0] not in do_not_alter, current_portfolio))

        # total of the portfolio to be updated
        total_value = self.getTotalWorthPortfolio(current_portfolio)

        # Nothing to do if current portfolio is empty
        if len(current_portfolio) == 0 or total_value == 0.0:
            print("Portfolio to liquidate is already empty")
            return

        # based on common base currency for current_portfolio
        target_portfolio = [(self.exchange.findBaseCurrency(current_portfolio),
                             total_value)]
        
        # filter out currencies from ignore list
        target_portfolio = list(filter(lambda x: x not in not_invest_list, target_portfolio))

        # Nothing to do if portfolio is empty
        if len(target_portfolio) == 0:
            raise BaseException()("Cannot find a portfolio to liquidate current portfolio to.")

        # Update the portfolio
        return self.__updatePortfolio(
            target_portfolio=target_portfolio,
            current_portfolio=current_portfolio,
            live_run=live_run)