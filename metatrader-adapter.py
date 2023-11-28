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

