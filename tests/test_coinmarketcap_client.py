from coinmarketcap_client import CoinMarketCapClient, LISTINGS_URL


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "status": {"error_code": 0},
            "data": [
                {"symbol": "USDT", "cmc_rank": 1},
                {"symbol": "ETH", "cmc_rank": 3},
                {"symbol": "BTC", "cmc_rank": 2},
            ],
        }


class FakeSession:
    def __init__(self):
        self.request = None

    def get(self, url, **kwargs):
        self.request = (url, kwargs)
        return FakeResponse()


def test_listings_are_ranked_and_stablecoins_excluded():
    session = FakeSession()
    client = CoinMarketCapClient("secret", session=session)

    assert client.getTopK(2) == ["BTC", "ETH"]
    url, kwargs = session.request
    assert url == LISTINGS_URL
    assert kwargs["headers"]["X-CMC_PRO_API_KEY"] == "secret"
    assert kwargs["params"] == {"start": 1, "limit": 109, "convert": "USD"}
    assert kwargs["timeout"] == 20


def test_api_status_error_is_reported():
    class ErrorResponse(FakeResponse):
        def json(self):
            return {"status": {"error_code": 1001, "error_message": "invalid key"}}

    class ErrorSession(FakeSession):
        def get(self, url, **kwargs):
            return ErrorResponse()

    try:
        CoinMarketCapClient("secret", session=ErrorSession())
    except RuntimeError as error:
        assert "invalid key" in str(error)
    else:
        raise AssertionError("an API status error must fail")
