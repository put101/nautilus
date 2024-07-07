# %%
file_name = "backtest_4_0.ipynb"
if file_name is None:
    file_name = __file__

# %%
# %%

import importlib

# ENVIRONMENT

import pandas as pd
import dotenv
import os

dotenv.load_dotenv(".env")

# DATA_PATH = os.environ["DATA_PATH"]
CATALOG_PATH = os.path.join(os.getcwd(), os.environ["CATALOG_PATH"])

# nautilus_trader imports

from nautilus_trader.model.position import Position
from nautilus_trader.model.objects import Price
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.config import (
    BacktestVenueConfig,
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestEngineConfig,
    RiskEngineConfig,
)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.trading.strategy import ImportableStrategyConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import (
    dt_to_unix_nanos,
    maybe_unix_nanos_to_dt,
    unix_nanos_to_dt,
)
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.cache.cache import Cache
import decimal

# other imports
from pandas import Timestamp
import importlib
import matplotlib.pyplot as plt

# my packages
from put101 import indicators
import strategies
from strategies import bollinger_cluster
from put101 import utils
from put101 import vizz

# ---------------- CONFIGURATION ----------------
catalog = ParquetDataCatalog(CATALOG_PATH)
start = dt_to_unix_nanos(pd.Timestamp("2023-01-01 00:00:00"))

end = start + pd.Timedelta(days=60).value

venue_str = "SIM_EIGHTCAP"
venue = Venue(venue_str)
symbol_str = "EURUSD"
symbol = Symbol(symbol_str)
instrument_id_str = f"EURUSD.{venue}"

instrument_id = InstrumentId(symbol, venue)
script_name = os.path.basename(file_name).split(".")[0]

IDENTIFIER = script_name

# %%
# %%
venue_configs = [
    BacktestVenueConfig(
        name=venue_str,
        oms_type="HEDGING",
        account_type="MARGIN",
        default_leverage=30,
        base_currency="USD",
        starting_balances=["10_000 USD"],
    ),
]

data_configs = [
    BacktestDataConfig(
        catalog_path=CATALOG_PATH,
        data_cls=QuoteTick,
        instrument_id=instrument_id,
        start_time=start,
        end_time=end,
    ),
]

strategies = [
    ImportableStrategyConfig(
        strategy_path="strategies.base_4:PUT101Strategy",
        config_path="strategies.base_4:PUT101StrategyConfig",
        config=dict(
            instrument_id=instrument_id.value,
            bar_type=f"{instrument_id}-5-MINUTE-BID-INTERNAL",
            IDENTIFIER=IDENTIFIER,
            bb_params=[
                (20, 2),
            ],
        ),
    ),
]

configs = [
    BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(
                log_level="INFO",
                log_level_file="DEBUG",
                log_file_format="json",
                log_directory="logs",
                log_file_name=f"backtest_{Timestamp.now()}.log",
            ),
            risk_engine=RiskEngineConfig(
                bypass=True,  # Example of bypassing pre-trade risk checks for backtests
            ),
        ),
        data=data_configs,
        venues=venue_configs,
    )
]

node = BacktestNode(configs)


# %%
# %%
results = node.run()

# %%
# %%

