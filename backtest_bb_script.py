# %%

import importlib

# ENVIRONMENT

import pandas as pd
import dotenv
import os

dotenv.load_dotenv('.env')
MT5_SERVER = os.environ["MT5_SERVER"]
MT5_LOGIN = os.environ["MT5_LOGIN"]
MT5_PASSWORD = os.environ["MT5_PASSWORD"]
DATA_PATH = os.environ["DATA_PATH"]
CATALOG_PATH = os.path.join(os.getcwd(), os.environ["CATALOG_PATH"])

# nautilus_trader imports

from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.config import BacktestVenueConfig, BacktestDataConfig, BacktestRunConfig, BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.trading.strategy import ImportableStrategyConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos, maybe_unix_nanos_to_dt, unix_nanos_to_dt
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.position import Position
from nautilus_trader.model.objects import Price
from decimal import Decimal

# other imports
from pandas import Timestamp
import importlib
import mplfinance as mpf
import matplotlib.pyplot as plt

# my packages
import put101.indicators as indicators
importlib.reload(indicators)

import strategies
importlib.reload(strategies)

import strategies.bollinger_cluster
importlib.reload(strategies.bollinger_cluster)
from strategies.bollinger_cluster import BollingerCluster


import put101.utils as utils
importlib.reload(utils)


# ---------------- CONFIGURATION ----------------
catalog = ParquetDataCatalog(CATALOG_PATH)
start = dt_to_unix_nanos(pd.Timestamp("2022-01-01 00:00:00"))

end = start + pd.Timedelta(days=180).value

venue_str = "SIM_EIGHTCAP"
venue = Venue(venue_str)
symbol_str = "EURUSD"
symbol = Symbol(symbol_str)
instrument_id_str = f"EURUSD.{venue}"

instrument_id = InstrumentId(symbol, venue)

# %%
venue_configs = [
    BacktestVenueConfig(
        name=venue_str,
        oms_type="HEDGING",
        account_type="MARGIN",
        default_leverage = 30,
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
        strategy_path="strategies.bollinger_cluster:BollingerCluster",
        config_path="strategies.bollinger_cluster:BollingerClusterConfig",
        config=dict(
            instrument_id=instrument_id.value,
            bar_type=f"{instrument_id}-15-MINUTE-BID-INTERNAL",
            bb_params=[
                (20, 2),
            ],
            USE_TRADING_HOURS=True,
            TRADING_SESSIONS=[(6,22), (8,11), (16,18), (21,22)],
            PARTIAL_RATIO=0.25
        ),
    ),
]

configs = [BacktestRunConfig(
    engine=BacktestEngineConfig(
        strategies=strategies,
    ),
    data=data_configs,
    venues=venue_configs,
)]

node = BacktestNode(configs)
print(strategies)

# %%
results = node.run()

# %%
res = results[0]
backtest_start = maybe_unix_nanos_to_dt(res.backtest_start)
backtest_end = maybe_unix_nanos_to_dt(res.backtest_end)
res

# %%
import put101.vizz as vizz

# This allows multiple outputs from a single jupyter notebook cell:
from IPython.core.interactiveshell import InteractiveShell
InteractiveShell.ast_node_interactivity = "all"

engine = node.get_engine(res.run_config_id)
strategy: BollingerCluster = engine.trader.strategies()[0]
cache: Cache = strategy.cache

main_t, main_s = strategy.get_main_plottable_indicators()
extra_plots = strategy.get_extra_plots()

layout = utils.get_layout(
                    res=res,
                    bars=strategy.bars,
                    overlay_indicators=main_t,
                    overlay_indicator_styles=main_s,
                    extra_plots=extra_plots,
                    positions=strategy.cache.positions(),
)

vizz.reset_output()
vizz.show(layout)

# %%
res
