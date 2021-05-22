#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
##
# Copyright (C) 2021 Parichay Kapoor <kparichay@gmail.com>
# @file   test_execute.py
# @date   22 May 2021
# @see
# @author Parichay Kapoor <kparichay@gmail.com>
# @bug    No known bugs except for NYI items
# @brief  Tests for execute_index_funds

import execute_index_fund

def test_exec_liquidate_01_p(capsys):
    ret_portfolio = execute_index_fund.main(['--liquidate', '--portfolio=ETH'])
    assert len(ret_portfolio) == 1
    assert ret_portfolio[0][0] == 'USDT'

def test_exec_liquidate_02_p(capsys):
    ret_portfolio = execute_index_fund.main(['--liquidate'])
    assert len(ret_portfolio) == 1
    assert ret_portfolio[0][0] == 'USDT'