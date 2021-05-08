#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   coinmarketcap_client.py
# @date   24 April 2021
# @see
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Client for the CoinMarketCap

from coinmarketcapapi import CoinMarketCapAPI

fiat_list = ["USDT", "USDC", "BUSD", "DAI", "UST", "PAX", "HUSD", "TUSD", "USDN"]
error_list = ["WBTC"]
LARGE_CAP = 20
MID_CAP = 50
SMALL_CAP = 100


class CoinMarketCapClient:
    """
    CoinMarketCap client to get the latest top listings sorted by market volume
    """

    def __init__(self, api_key, ignore_list=fiat_list + error_list):
        # Never invest in fiat
        self.ignore_list = list(set(ignore_list + fiat_list))

        self.client = CoinMarketCapAPI(api_key=api_key)
        self.latest_listing_response = self.client.cryptocurrency_listings_latest()
        if self.latest_listing_response.status["error_code"] != 0:
            raise BaseException(
                "Getting latest listings failed with error code {}".format(
                    self.latest_listing_response.status["error_code"]
                )
            )

        self.sorted_listing = sorted(
            self.latest_listing_response.data, key=lambda x: x["cmc_rank"]
        )
        self.sorted_listing = [x["symbol"] for x in self.sorted_listing]
        self.sorted_listing = list(
            filter(lambda x: x not in self.ignore_list, self.sorted_listing)
        )

    def __getTopK(self, ignore, k):
        return self.sorted_listing[ignore:k]

    def getTopK(self, k):
        return self.__getTopK(0, k)

    def getLargeCap(self):
        return self.getTopK(LARGE_CAP)

    def getMidCap(self):
        return self.__getTopK(LARGE_CAP, MID_CAP)

    def getSmallCap(self):
        return self.__getTopK(MID_CAP, SMALL_CAP)
