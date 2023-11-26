"""
I want to write a very basic metatrader adapter that will allow me to
- send buy/sell orders
- get current balance
- get current open positions
- get current open orders

"""

import asyncio
import logging
import sys
import time
from typing import List, Optional

import MetaTrader5 as mt5



""""Documentation of metatrader5 package:
https://www.mql5.com/en/docs/integration/python_metatrader5
MetaTrader module for integration with Python

MQL5 is designed for the development of high-performance trading applications in the financial markets and is unparalleled among other specialized languages used in the algorithmic trading. The syntax and speed of MQL5 programs are very close to C++, there is support for OpenCL and integration with MS Visual Studio. Statistics, fuzzy logic and ALGLIB libraries are available as well. MetaEditor development environment features native support for .NET libraries with "smart" functions import eliminating the need to develop special wrappers. Third-party C++ DLLs can also be used.  C++ source code files (CPP and H) can be edited and compiled into DLL directly from the editor. Microsoft Visual Studio installed on user's PC can be used for that.

Python is a modern high-level programming language for developing scripts and applications. It contains multiple libraries for machine learning, process automation, as well as data analysis and visualization.

MetaTrader package for Python is designed for convenient and fast obtaining of exchange data via interprocessor communication directly from the MetaTrader 5 terminal. The data received this way can be further used for statistical calculations and machine learning.

Installing the package from the command line:

  pip install MetaTrader5

Updating the package from the command line:

  pip install --upgrade MetaTrader5

Functions for integrating MetaTrader 5 and Python

Function
	

Action

initialize
	

Establish a connection with the MetaTrader 5 terminal

login
	

Connect to a trading account using specified parameters

shutdown
	

Close the previously established connection to the MetaTrader 5 terminal

version
	

Return the MetaTrader 5 terminal version

last_error
	

Return data on the last error

account_info
	

Get info on the current trading account

terminal_Info
	

Get status and parameters of the connected MetaTrader 5 terminal

symbols_total
	

Get the number of all financial instruments in the MetaTrader 5 terminal

symbols_get
	

Get all financial instruments from the MetaTrader 5 terminal

symbol_info
	

Get data on the specified financial instrument

symbol_info_tick
	

Get the last tick for the specified financial instrument

symbol_select
	

Select a symbol in the MarketWatch window or remove a symbol from the window

market_book_add
	

Subscribes the MetaTrader 5 terminal to the Market Depth change events for a specified symbol

market_book_get
	

Returns a tuple from BookInfo featuring Market Depth entries for the specified symbol

market_book_release
	

Cancels subscription of the MetaTrader 5 terminal to the Market Depth change events for a specified symbol

copy_rates_from
	

Get bars from the MetaTrader 5 terminal starting from the specified date

copy_rates_from_pos
	

Get bars from the MetaTrader 5 terminal starting from the specified index

copyrates_range
	

Get bars in the specified date range from the MetaTrader 5 terminal

copy_ticks_from
	

Get ticks from the MetaTrader 5 terminal starting from the specified date

copy_ticks_range
	

Get ticks for the specified date range from the MetaTrader 5 terminal

orders_total
	

Get the number of active orders.

orders_get
	

Get active orders with the ability to filter by symbol or ticket

order_calc_margin
	

Return margin in the account currency to perform a specified trading operation

order_calc_profit
	

Return profit in the account currency for a specified trading operation

order_check
	

Check funds sufficiency for performing a required trading operation

order_send
	

Send a request to perform a trading operation.

positions_total
	

Get the number of open positions

positions_get
	

Get open positions with the ability to filter by symbol or ticket

history_orders_total
	

Get the number of orders in trading history within the specified interval

history_orders_get
	

Get orders from trading history with the ability to filter by ticket or position

history_deals_total
	

Get the number of deals in trading history within the specified interval

history_deals_get
	

Get deals from trading history with the ability to filter by ticket or position

"""

