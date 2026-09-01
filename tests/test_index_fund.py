from index_fund import IndexFund


class FakeExchange:
    def __init__(self):
        self.balance = [("USDT", 100.0), ("ETH", 400.0)]
        self.orders = []

    def getBalanceUsd(self, cached=True, ignore_small_amounts=20):
        return self.balance

    def getSupportedPortfolio(self, portfolio):
        return portfolio

    def findBaseCurrency(self, portfolio):
        return "USDT", []

    def getPairPrice(self, symbol, base):
        return 1.0

    def getUsdSymbol(self):
        return "USDT"

    def buyOrder(self, symbol, base, value, live_run):
        self.orders.append(("BUY", symbol, base, value, live_run))
        return value

    def sellOrder(self, symbol, base, value, live_run):
        self.orders.append(("SELL", symbol, base, value, live_run))
        return value


def test_reinvest_sells_and_buys_to_equal_weights():
    exchange = FakeExchange()
    result = IndexFund(exchange).reinvest(["BTC", "ETH"], live_run=False)

    assert result == [("BTC", 250.0), ("ETH", 250.0)]
    assert exchange.orders == [
        ("SELL", "ETH", "USDT", 150.0, False),
        ("BUY", "BTC", "USDT", 250.0, False),
    ]


def test_rebalance_already_at_target_does_not_divide_by_zero():
    exchange = FakeExchange()
    result = IndexFund(exchange).rebalance(
        ["ETH", "USDT"], weight=[4, 1], live_run=False
    )

    assert result == [("ETH", 400.0), ("USDT", 100.0)]
    assert exchange.orders == []


def test_liquidate_uses_common_base_currency():
    exchange = FakeExchange()
    result = IndexFund(exchange).liquidate(portfolio=["ETH"], live_run=False)

    assert result == [("USDT", 400.0)]
    assert exchange.orders == [("SELL", "ETH", "USDT", 400.0, False)]


def test_missing_common_quote_pair_fails_before_orders():
    class UnroutableExchange(FakeExchange):
        def findBaseCurrency(self, portfolio):
            return "USDT", ["BTC"]

    exchange = UnroutableExchange()
    try:
        IndexFund(exchange).reinvest(["BTC", "ETH"], live_run=False)
    except ValueError as error:
        assert "complete plan" in str(error)
    else:
        raise AssertionError("a plan with no common quote currency must fail")
    assert exchange.orders == []
