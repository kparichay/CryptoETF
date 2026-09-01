from binance_client import BinanceClient


class FakeSpotApi:
    def __init__(self):
        self.orders = []

    def get_exchange_info(self):
        return {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.001",
                            "stepSize": "0.001",
                        },
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                    ],
                },
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.00001",
                            "stepSize": "0.00001",
                        },
                        {"filterType": "NOTIONAL", "minNotional": "10"},
                    ],
                },
                {
                    "symbol": "BTCUPUSDT",
                    "baseAsset": "BTCUP",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [],
                },
                {
                    "symbol": "BTCDOWNUSDT",
                    "baseAsset": "BTCDOWN",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [],
                },
            ]
        }

    def get_all_tickers(self):
        return [
            {"symbol": "ETHUSDT", "price": "2000"},
            {"symbol": "BTCUSDT", "price": "50000"},
            {"symbol": "BTCUPUSDT", "price": "10"},
            {"symbol": "BTCDOWNUSDT", "price": "10"},
        ]

    def get_account(self):
        return {
            "balances": [
                {"asset": "USDT", "free": "100"},
                {"asset": "ETH", "free": "0.1"},
            ]
        }

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {
            "status": "FILLED",
            "cummulativeQuoteQty": kwargs.get("quoteOrderQty", "25"),
        }


def test_prices_balances_and_dry_orders_use_current_spot_contract():
    api = FakeSpotApi()
    client = BinanceClient("key", "secret", client=api)

    assert client.getPairPrice("ETH", "USDT") == 2000.0
    assert client.getBalanceUsd() == [("ETH", 200.0), ("USDT", 100.0)]
    assert client.buyOrder("BTC", "USDT", 25, live_run=False) == 24.975
    assert api.orders == []


def test_live_market_buy_uses_quote_order_quantity():
    api = FakeSpotApi()
    client = BinanceClient("key", "secret", client=api)

    client.buyOrder("BTC", "USDT", 25, live_run=True)

    assert api.orders == [
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": "24.975",
        }
    ]


def test_live_market_sell_uses_lot_size_quantity():
    api = FakeSpotApi()
    client = BinanceClient("key", "secret", client=api)

    client.sellOrder("BTC", "USDT", 25, live_run=True)

    assert api.orders == [
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "MARKET",
            "quantity": "0.00049",
        }
    ]


def test_minimum_notional_skips_the_order():
    api = FakeSpotApi()
    client = BinanceClient("key", "secret", client=api)

    assert client.buyOrder("BTC", "USDT", 5, live_run=True) == 0.0
    assert api.orders == []


def test_leveraged_token_helpers_remain_available():
    client = BinanceClient("key", "secret", client=FakeSpotApi())

    assert client.getLeveragedCurrencies() == ["BTC"]
    assert client.getBullSymbol("BTC") == "BTCUP"
    assert client.getBearSymbol("BTC") == "BTCDOWN"
    assert client.getDeleveragizedSymbol("BTCUP") == "BTC"
