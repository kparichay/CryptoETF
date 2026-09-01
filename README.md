# Crypto Index Funds

Build and manage self-managed cryptocurrency index funds with Binance. The
current implementation targets Binance Spot.

## Dependencies

- Python 3.10+
- `python-binance` 1.0.37+
- CoinMarketCap `/v3/cryptocurrency/listings/latest` for named funds

The old `python-coinmarketcap` wrapper has been replaced with a small API
client in this repository.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
cp keys.sample keys
```

Add Binance API credentials to `[binance]` in `keys`. A `[coinmarketcap]`
`api_key` is needed for named funds. Use a Spot-only key with no withdrawal
permission.

## Funds

- Large Cap: top 20 assets
- Medium Cap: next 30 assets (ranks 21–50)
- Small Cap: next 50 assets (ranks 51–100)

Assets are equally weighted by default. You can create custom funds by choosing
your own assets and weights.

## Functionality

- **Rebalance**: rebalance a portfolio to supplied weights, or equal weights by
  default.
- **Reinvest**: move a subset or the full portfolio into a new portfolio.
- **Liquidate**: liquidate a portfolio into a common quote currency.
- **Leverage Bull/Bear/Liquidate**: the intended project scope includes moving
  between non-leveraged and leveraged tokens. It is not available in the
  current CLI because there is no complete supported implementation.

Binance requires acceptance of its [leveraged-token terms](https://www.binance.com/en/trade/BTCUP_USDT?layout=basic&type=spot)
and quiz before it allows leveraged-token trading.

## Usage

Commands are dry runs unless `--live --yes` is supplied.

```bash
# Equal-weight BTC and ETH
python execute_index_fund.py --rebalance --portfolio BTC ETH

# 70/30 BTC/ETH from 500 USD of USDT
python execute_index_fund.py --rebalance --portfolio BTC ETH --weight 70 30 \
  --source-portfolio USDT --source-amount 500

# Large-cap fund; requires a CoinMarketCap key
python execute_index_fund.py --reinvest --portfolio Large \
  --source-portfolio USDT --source-amount 100

# Binance Spot Testnet
python execute_index_fund.py --reinvest --testnet --portfolio BTC ETH
```

Current Binance API usage: market buys use `quoteOrderQty`; market sells use a
`LOT_SIZE`-rounded quantity. `NOTIONAL` and `MIN_NOTIONAL` filters are handled.
Use `--tld us` for Binance.US and `--help` for all options.

## Development

```bash
python -m pytest
```

The tests are offline; use a dry run and then Testnet before a live order.

## Support

Contributions for new features and exchanges are welcome.
