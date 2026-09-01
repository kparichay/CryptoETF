import execute_index_fund


class FakeBinanceClient:
    def __init__(self, **kwargs):
        self.balance = [("USDT", 100.0)]

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
        return value

    def sellOrder(self, symbol, base, value, live_run):
        return value


def test_dry_run_reinvest_uses_credentials_file_and_never_sets_live(
    tmp_path, monkeypatch
):
    keys = tmp_path / "keys"
    keys.write_text("[binance]\napi_key = key\nsecret_key = secret\n")
    monkeypatch.setattr(execute_index_fund, "BinanceClient", FakeBinanceClient)

    result = execute_index_fund.main(
        [
            "--reinvest",
            "--keys",
            str(keys),
            "--portfolio",
            "BTC",
            "ETH",
        ]
    )

    assert result == [("BTC", 50.0), ("ETH", 50.0)]


def test_live_run_requires_explicit_acknowledgement(tmp_path):
    keys = tmp_path / "keys"
    keys.write_text("[binance]\napi_key = key\nsecret_key = secret\n")

    try:
        execute_index_fund.main(["--liquidate", "--keys", str(keys), "--live"])
    except ValueError as error:
        assert "--yes" in str(error)
    else:
        raise AssertionError("live runs must require --yes")


def test_market_cap_selector_requires_a_coinmarketcap_key(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.write_text("[binance]\napi_key = key\nsecret_key = secret\n")
    monkeypatch.setattr(execute_index_fund, "BinanceClient", FakeBinanceClient)

    try:
        execute_index_fund.main(
            ["--reinvest", "--keys", str(keys), "--portfolio", "Large"]
        )
    except ValueError as error:
        assert "coinmarketcap" in str(error)
    else:
        raise AssertionError("a selector without a CoinMarketCap key must fail")


def test_source_amount_must_match_source_portfolio(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.write_text("[binance]\napi_key = key\nsecret_key = secret\n")
    monkeypatch.setattr(execute_index_fund, "BinanceClient", FakeBinanceClient)

    try:
        execute_index_fund.main(
            [
                "--reinvest",
                "--keys",
                str(keys),
                "--portfolio",
                "BTC",
                "--source-portfolio",
                "USDT",
                "ETH",
                "--source-amount",
                "100",
            ]
        )
    except ValueError as error:
        assert "--source-amount" in str(error)
    else:
        raise AssertionError("mismatched source amounts must fail")
