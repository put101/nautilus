import importlib
import pandas as pd
import dotenv
import os
import pathlib
import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

import sys
#print("appending to sys path: ", os.path.abspath("."))
#sys.path.append(os.path.abspath("."))
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
from pandas import Timestamp
import importlib
import matplotlib.pyplot as plt

# ===================================
#   (               (               
#   )\              )\ )  (   (  (  
# (((_)   (    (   (()/(  )\  )\))( 
# )\___   )\   )\ ) /(_))((_)((_))\ 
#((/ __| ((_) _(_/((_) _| (_) (()(_)
# | (__ / _ \| ' \))|  _| | |/ _` | 
#  \___|\___/|_||_| |_|   |_|\__, | 
#                            |___/  
# -----------------------------------
logger.info("Stage: Config.")

# get version from folder name of this file
VERSION = pathlib.Path(__file__).parent.name
IDENTIFIER = "backtest_v2000" + "_run_" + "3"
NAUTILUS_LOG_LEVEL = "INFO"
NAUTILUS_LOG_LEVEL_FILE = "DEBUG"
ROOT_LOG_LEVEL = logging.DEBUG
ROOT_LOG_LEVEL_FILE = logging.DEBUG
SKIP_BACKTEST_RUN = False
WAIT_FOR_INPUT = False

# log all upper case constants dynamically
for name in dir():
    if name.isupper():
        logger.info(f"{name}: {str(eval(name))}")        

# ===================================


#    ██████ ▓█████▄▄▄█████▓ █    ██  ██▓███  
#  ▒██    ▒ ▓█   ▀▓  ██▒ ▓▒ ██  ▓██▒▓██░  ██▒
#  ░ ▓██▄   ▒███  ▒ ▓██░ ▒░▓██  ▒██░▓██░ ██▓▒
#    ▒   ██▒▒▓█  ▄░ ▓██▓ ░ ▓▓█  ░██░▒██▄█▓▒ ▒
#  ▒██████▒▒░▒████▒ ▒██▒ ░ ▒▒█████▓ ▒██▒ ░  ░
#  ▒ ▒▓▒ ▒ ░░░ ▒░ ░ ▒ ░░   ░▒▓▒ ▒ ▒ ▒▓▒░ ░  ░
#  ░ ░▒  ░ ░ ░ ░  ░   ░    ░░▒░ ░ ░ ░▒ ░     
#  ░  ░  ░     ░    ░       ░░░ ░ ░ ░░       
#        ░     ░  ░           ░              



logger.info("Stage: Setup.")
dotenv.load_dotenv(verbose=True, override=True)

PROJECT_ROOT = pathlib.Path(os.environ.get("NAUTILUS_PROJECT_ROOT"))
if PROJECT_ROOT is None:
    logger.error("NAUTILUS_PROJECT_ROOT environment variable is not set.")
    raise EnvironmentError("NAUTILUS_PROJECT_ROOT environment variable is not set.")

dotenv.load_dotenv(PROJECT_ROOT / "docker" / ".env", override=True)

# DATA_PATH = os.environ["DATA_PATH"]
CATALOG_PATH = str(PROJECT_ROOT / os.environ["CATALOG_PATH"])
CATALOG_PATH = './catalog/'

catalog = ParquetDataCatalog(CATALOG_PATH)
start = dt_to_unix_nanos(pd.Timestamp("2020-01-01 00:00:00"))
end = start + pd.Timedelta(days=120).value

venue_str = "SIM_EIGHTCAP"
venue = Venue(venue_str)
symbol_str = "EURUSD"
symbol = Symbol(symbol_str)
instrument_id_str = f"EURUSD.{venue}"
instrument_id = InstrumentId(symbol, venue)

venue_configs = [
    BacktestVenueConfig(
        name=venue_str,
        oms_type="HEDGING",
        account_type="MARGIN",
        default_leverage=500,
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
        strategy_path=f"{VERSION}.base:PUT101Strategy",
        config_path=f"{VERSION}.base:PUT101StrategyConfig",
        config=dict(
            environment=os.environ.copy(),
            instrument_id=instrument_id.value,
            bar_type=f"{instrument_id}-5-MINUTE-BID-INTERNAL",
            IDENTIFIER=IDENTIFIER,
            bb_params=[
                (20, 2),
                (25, 2),
                (30, 2),
            ],
            TP_PIPS=0,
            SL_PIPS=10,
            RR=2.5,
        ),
    ),
]

configs = [
    BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(
                log_level=NAUTILUS_LOG_LEVEL,
                log_level_file=NAUTILUS_LOG_LEVEL_FILE,
                log_file_format="text",
                log_directory="logs",
                log_file_name=f"bt_{Timestamp.now()}.log",
            ),
            risk_engine=RiskEngineConfig(
                bypass=True,  # Example of bypassing pre-trade risk checks for backtests
            ),
        ),
        data=data_configs,
        venues=venue_configs,
    )
]

logger.info("Configs created")
logger.debug(f"Configs: {configs}")

logger.info("Creating BacktestNode")
node = BacktestNode(configs)

if not SKIP_BACKTEST_RUN:
    logger.info("Stage: Running backtest.")
    if WAIT_FOR_INPUT:
        input("Press Enter to continue...")
    results = node.run(raise_exception=True)
    logger.info("Stage: Backtest completed.")

