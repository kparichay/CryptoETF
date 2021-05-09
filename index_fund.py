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

    def __executeTrades(self, trades, tradeFunc, live_run):
        self_trades = list(filter(lambda x: x[0][0] == x[0][1], trades))
        non_self_trades = list(filter(lambda x: x[0][0] != x[0][1], trades))
        self_trades_amount = sum([quant for symbol, quant in non_self_trades])
        non_self_trades_amount = sum([tradeFunc(symbol[0], symbol[1], quant, live_run)
            for symbol, quant in non_self_trades])
        return self_trades_amount + non_self_trades_amount
            

    def __liquidateTrades(self, trades, live_run):
        return self.__executeTrades(trades,
                                     self.exchange.sellOrder, live_run)

    def __investTrades(self, trades, live_run):
        return self.__executeTrades(trades,
                                     self.exchange.buyOrder, live_run)

    def __createTrades(self, liquidate_portfolio, invest_portfolio):
        if len(liquidate_portfolio) == 0 and len(invest_portfolio) == 0:
            return [], []

        ## TODO: create a graph setup that would find on with multiple base currencies for trading
        base_currency, missing_currencies = self.exchange.findBaseCurrency(liquidate_portfolio +
                                                       invest_portfolio)

        if len(missing_currencies) > 0:
            print('Warn: Coins ', missing_currencies, ' will not be traded due to limited trade pairs availability')

        # Reduced amount available for liquidity/invest will be handled later by accounting the exact amount liquidated
        liquidate_portfolio = [x for x in liquidate_portfolio if x[0] not in missing_currencies]
        invest_portfolio = [x for x in invest_portfolio if x[0] not in missing_currencies]

        base_price = self.exchange.getPairPrice(base_currency, self.exchange.getUsdSymbol())

        def portfolio_to_trades(portfolio):
            return [((x[0], base_currency), x[1]/base_price) for x in portfolio]

        liquidate_trades = portfolio_to_trades(liquidate_portfolio)
        invest_trades = portfolio_to_trades(invest_portfolio)

        return liquidate_trades, invest_trades


    def __updatePortfolio(self,
                          target_portfolio,
                          current_portfolio,
                          live_run=False):

        # update target_portfolio based on available symbols on the exchange
        orig_target_portfolio = target_portfolio
        target_portfolio = self.exchange.getSupportedPortfolio(target_portfolio)

        # Update the portfolio
        print("##################################################")
        print("Current Portfolio -> \n", current_portfolio)
        print("##################################################")
        print("Target Portfolio -> \n", target_portfolio)
        print("##################################################")

        if target_portfolio != orig_target_portfolio:
            print('Target portfolio has been updated given the exchange supported currencies')
            input("Press any key to continue:")

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

        # convert portfolio to trades
        liquidate_trades, invest_trades = self.__createTrades(liquidate_portfolio, invest_portfolio)

        # execute the trades
        if live_run:
            print("Executing Trades (LIVE) -> ")
        else:
            print("Executing Trades (NOT LIVE) -> ")

        liquidated_amount = self.__liquidateTrades(liquidate_trades, live_run)

        # scale down the invest portfolio by the amount which has been aggregated by the sales
        amount_required = sum([x[1] for x in invest_trades])
        invest_trades = [(x[0], x[1] / amount_required * liquidated_amount)
                            for x in invest_trades]

        self.__investTrades(invest_trades, live_run)
        print("##################################################")

        if not live_run:
            updated_portfolio = target_portfolio
        else:
            # Return the updated portfolio
            updated_portfolio = self.getCurrentPortfolio(cached=False)
            target_symbols = [x[0] for x in target_portfolio]
            updated_portfolio = [x for x in updated_portfolio if x[0] in target_symbols]

        print("Updated Portfolio -> \n", updated_portfolio)
        print("##################################################")
        print('NOTE: Uupdated Portfolio can be outdated for live mode due to limitation of the exchange API.')

        return updated_portfolio

    def __createPortfolioFromSource(self, source_currencies, source_amount):
        current_portfolio = self.getCurrentPortfolio()

        # intersect with source_currencies
        if len(source_currencies) > 0:
            current_portfolio = list(
                filter(lambda x: x[0] in source_currencies, current_portfolio))
            if len(source_amount) > 0:
                assert(len(source_amount) == len(source_currencies))
                source_portfolio = list(zip(source_currencies, source_amount))
                for bc, ba in source_portfolio:
                    if len(list(filter(lambda x: x[0] == bc and x[1] >= ba, current_portfolio))) != 1:
                        raise BaseException(
                            "Given base amount exceeds the amount in wallet")
                    
                current_portfolio = source_portfolio

        return current_portfolio

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

        # create current portfolio given the source info
        current_portfolio = self.__createPortfolioFromSource(source_currencies, source_amount)

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

    def leverage(self,
        mode,   # can be bear or bull 
        portfolio,
        source_currencies=[],
        source_amount=[],
        not_invest_list=[],
        do_not_alter=[],
        weight=None,
        live_run=False):

        # if portfolio not provided, use full current portfolio
        if portfolio is not None or (portfolio and len(portfolio) > 0):
            raise BaseException('Portfolio not accepted with bear/bull options.')

        portfolio = self.__createPortfolioFromSource(source_currencies, source_amount)

        if mode == 'liquidate':
            target_portfolio = [(self.exchange.getDeleveragizedSymbol(x[0]), x[1]) for x in portfolio]
            target_portfolio = [x for x in target_portfolio if x not in portfolio]
        else:
            leveraged_currencies = self.exchange.getLeveragedCurrencies()
            portfolio = [x for x in portfolio if x[0] in leveraged_currencies]

            if mode == 'bull':
                target_portfolio = [(self.exchange.getBullSymbol(x[0]), x[1]) for x in portfolio]
            elif mode == 'bear':
                target_portfolio = [(self.exchange.getBearSymbol(x[0]), x[1]) for x in portfolio]
            else:
                raise BaseException('Unsupported mode for leverage.')

        if len(not_invest_list) > 0 or len(do_not_alter) > 0:
            raise BaseException('not_invest_list or do_not_alter not supported in leveraging.')

        source_currencies = [x[0] for x in portfolio]
        source_amount = [x[1] for x in portfolio]
        weight = [x[1] for x in target_portfolio]
        portfolio = [x[0] for x in target_portfolio]

        if portfolio == []:
            raise BaseException('Provided currencies cannot be leveraged or are already leveraged.')

        return self.reinvest(
            portfolio=portfolio,
            source_currencies=source_currencies,
            source_amount=source_amount,
            not_invest_list=not_invest_list,
            do_not_alter=do_not_alter,
            weight=weight,
            live_run=live_run,
        )