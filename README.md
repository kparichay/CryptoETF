# Crypto Index Funds 

This repository provides index funds for cryptocurrency with binance. This document is a work in progress and will soon be updated.

# Dependencies

- python-binance: [Binance Client](https://github.com/sammchardy/python-binance)
- python-coinmarketcap: [CoinMarketCap Client](https://github.com/rsz44/python-coinmarketcap)

Note: If these packages break, I will add my own API wrappers.

# Funds

- Large Cap - top 20 funds
- Medium Cap - next 30 funds (under top 50)
- Small Cap - next 50 funds (under top 100)

Note: Each currency is weighted equally.

# Customizations

Feel free to create your own funds based on different cyptocurrencies listing and their weightages.

# Functionalities

Multiple functionalities are supported to manage your portfolio along with leveraging.

## Rebalance

Rebalances the given portfolio to the given weights or to the equal weightage by default.

## Reinvest

Reinvest a subsection or full existing portfolio to new portfolios.

## Liquidate

Liquidate given portfolio to fiat selected currencies.

## Leverage Bull/Bear/Liquidate

Invest the portfolio into leveraged tokens with bull or bear side, or liquidate leveraged position to non-leveraged portfolio.

One will have to go to the binance website and agree to the [terms and conditions](https://www.binance.com/en/trade/BTCUP_USDT?layout=basic&type=spot) for trading leveraged tokens, and take the quiz before trading leveraged tokens will be allowed by binance.


# Support

Feel free to add PR if you want to new feature or support other exchange.