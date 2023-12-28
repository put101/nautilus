from nautilus_trader.model.position import Position
from nautilus_trader.cache.cache import Cache
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.engine import Trader, BacktestEngine
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.model.identifiers import Venue, InstrumentId
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.config import BacktestVenueConfig, BacktestDataConfig, BacktestRunConfig, BacktestEngineConfig
from nautilus_trader.trading.strategy import ImportableStrategyConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos, maybe_unix_nanos_to_dt
from nautilus_trader.portfolio.portfolio import PortfolioAnalyzer

from decimal import Decimal
import pandas as pd
conf: BacktestRunConfig
def visualize_backtest(engine: BacktestEngine):
    run_config_id = engine.run_config_id
    trader: Trader = engine.trader
    machine_id:str = engine.machine_id
    run_id:str = engine.run_id
    instance_id:str = engine.instance_id

    print(engine)
    pass