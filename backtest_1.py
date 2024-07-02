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

end = start + pd.Timedelta(days=30).value

venue_str = "SIM_EIGHTCAP"
venue = Venue(venue_str)
symbol_str = "EURUSD"
symbol = Symbol(symbol_str)
instrument_id_str = f"EURUSD.{venue}"

instrument_id = InstrumentId(symbol, venue)
script_name = os.path.basename(__file__).split(".")[0]

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
        strategy_path="strategies.base_1:PUT101Strategy",
        config_path="strategies.base_1:PUT101StrategyConfig",
        config=dict(
            instrument_id=instrument_id.value,
            bar_type=f"{instrument_id}-15-MINUTE-BID-INTERNAL",
        ),
    ),
]

configs = [
    BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(
                log_level="ERROR",
                log_level_file="DEBUG",
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
results = node.run()

# %%
res = results[0]
backtest_start = maybe_unix_nanos_to_dt(res.backtest_start)
backtest_end = maybe_unix_nanos_to_dt(res.backtest_end)
res


engine = node.get_engine(res.run_config_id)
strategy: bollinger_cluster.BollingerCluster = engine.trader.strategies()[0]
cache: Cache = strategy.cache

main_t, main_s = strategy.get_main_plottable_indicators()
extra_plots = strategy.get_extra_plots()

layout = utils.get_layout(
    res=res,
    script_name=script_name,
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
