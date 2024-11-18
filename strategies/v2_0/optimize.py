import matplotlib.pyplot as plt
import importlib
from pandas import Timestamp
import numpy as np
import decimal
from nautilus_trader.cache.cache import Cache
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.core.datetime import (
    dt_to_unix_nanos,
    maybe_unix_nanos_to_dt,
    unix_nanos_to_dt,
)
from nautilus_trader.config import LoggingConfig
from nautilus_trader.trading.strategy import ImportableStrategyConfig
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import (
    BacktestVenueConfig,
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestEngineConfig,
    RiskEngineConfig,
)
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.objects import Price
from nautilus_trader.model.position import Position
import sys
import optuna
import pandas as pd
import dotenv
import os
import pathlib
import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# print("appending to sys path: ", os.path.abspath("."))
# sys.path.append(os.path.abspath("."))

# ===================================
#   (               (
#   )\              )\ )  (   (  (
# (((_)   (    (   (()/(  )\  )\))(
# )\___   )\   )\ ) /(_))((_)((_))\
# ((/ __| ((_) _(_/((_) _| (_) (()(_)
# | (__ / _ \| ' \))|  _| | |/ _` |
#  \___|\___/|_||_| |_|   |_|\__, |
#                            |___/
# -----------------------------------

NAUTILUS_LOG_LEVEL = "INFO"
NAUTILUS_LOG_LEVEL_FILE = "DEBUG"
ROOT_LOG_LEVEL = logging.DEBUG
ROOT_LOG_LEVEL_FILE = logging.DEBUG
SKIP_BACKTEST_RUN = False
WAIT_FOR_INPUT = False

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


optimzation_goals = (
        ("Profit Factor", "maximize"),
        ("Expectancy", "maximize"),
        ("PnL% (total)", "maximize"),
        #("Win Rate", "maximize"),
    )

EXPERIMENT = "0"
VERSION = pathlib.Path(__file__).parent.name
STUDY_NAME = f"bt_{VERSION}_experiment_{EXPERIMENT}"

N_TRIALS = 10

def create_backtest_config(trial):
    
    IDENTIFIER = f"{STUDY_NAME}_trial_{trial.number}"
    NAUTILUS_LOG_LEVEL = "INFO"
    NAUTILUS_LOG_LEVEL_FILE = "DEBUG"

    # Optuna hyperparameter suggestions
    bb_period = trial.suggest_int('bb_period', 10, 50)
    bb_std = trial.suggest_float('bb_std', 1.0, 3.0)
    tp_pips = trial.suggest_int('tp_pips', 0, 0)
    sl_pips = trial.suggest_int('sl_pips', 5, 50)
    risk_reward = trial.suggest_float('risk_reward', 0.1, 50.0)

    # Setup venue and instrument configuration
    venue_str = "SIM_EIGHTCAP"
    venue = Venue(venue_str)
    symbol_str = "EURUSD"
    symbol = Symbol(symbol_str)
    instrument_id = InstrumentId(symbol, venue)

    start = dt_to_unix_nanos(pd.Timestamp("2020-01-01 00:00:00"))
    end = start + pd.Timedelta(days=30).value

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
                    (bb_period, bb_std),
                ],
                TP_PIPS=tp_pips,
                SL_PIPS=sl_pips,
                RR=risk_reward,
            ),
        ),
    ]

    return BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            trader_id=f"BACKTESTER-{trial.number:03d}",
            logging=LoggingConfig(
                log_level=NAUTILUS_LOG_LEVEL,
                log_level_file=NAUTILUS_LOG_LEVEL_FILE,
                log_file_format="text",
                log_directory="logs",
                log_file_name=f"bt_trial_{trial.number}.log",
            ),
            risk_engine=RiskEngineConfig(bypass=True),
        ),
        data=data_configs,
        venues=venue_configs,
    )


def objective(trial):
    """

    Args:
        trial (_type_): _description_

    Returns:
        _type_: _description_


    BacktestResult(trader_id='BACKTESTER-020', machine_id='Tobiass-MacBook-Air.local', 
        run_config_id='c9c59a0e8852e56362ca50bc5b19fbe35b09db228fd72646c0b6a2e8823c0bbb', 
        instance_id='3ce5c3c2-b3a8-44a6-a73e-58c3414a7049', run_id='785f94d0-c6a2-47fa-9c46-2ebc4cc3f77c', 
        run_started=1731712539884419000, run_finished=1731712540631042000, backtest_start=1577923200490000000, 
        backtest_end=1578095873505000000, elapsed_time=172673.015, iterations=0, total_events=42, total_orders=15, 
        total_positions=5, 
        stats_pnls={'USD': {
            'PnL (total)': 521.89, 
            'PnL% (total)': 5.218899999999994, 
            'Max Winner': 469.53, 
            'Avg Winner': 469.53, 
            'Min Winner': 469.53, 
            'Min Loser': -2.23, 
            'Avg Loser': -139.05666666666667, 
            'Max Loser': -210.46, 
            'Expectancy': 104.37800000000001, 
            'Win Rate': 0.4
        }}, 
        stats_returns={
            'Returns Volatility (252 days)': 0.00040042265577980643, 
            'Average (Return)': 0.0012052330297631442, 
            'Average Loss (Return)': -0.0018180739706978896, 
            'Average Win (Return)': 0.004228540030224178, 
            'Sharpe Ratio (252 days)': 0.16610902877391906, 
            'Sortino Ratio (252 days)': nan, 
            'Profit Factor': 2.325834976120912, 
            'Risk Return Ratio': 0.3139602761997963
        })
    """

    logger.info(f"Trial {trial.number}")

    config = create_backtest_config(trial)
    
    trial.set_user_attr("config", str(config))
    
    node = BacktestNode([config])

    try:
        results = node.run(raise_exception=True)

        res: BacktestResult = results[0]
        
        trial.set_user_attr("results", str(res))
        
        node.dispose()
        del node
        
        metrics = res.stats_pnls['USD'].copy()
        metrics.update(res.stats_returns)
        
        return [ ( metrics[m] if not np.isnan(metrics[m]) else (0 if d=='maximize' else np.inf)) for m, d in optimzation_goals ]
    except Exception as e:
        logger.error(f"Exception in objective: {e}")
        return [ 0 if d=='maximize' else np.inf for m,d in optimzation_goals]
        


def optimize_strategy():
    study = optuna.create_study(directions=[direction for _, direction in optimzation_goals], 
                                storage='sqlite:///optuna.db',
                                study_name=STUDY_NAME, 
                                load_if_exists=True)

    study.optimize(objective, n_trials=N_TRIALS, n_jobs=1)

    logger.info("Best trials:")
    trials = study.best_trials
    for t in trials:
        logger.info(f"Trial number: {t.number}")
        logger.info(f"Value: {t.values}")
        logger.info("Params: ")
        for key, value in t.params.items():
            logger.info(f"\t{key}: {value}")

    return [study.best_trials]


if __name__ == "__main__":
    dotenv.load_dotenv(verbose=True, override=True)

    PROJECT_ROOT = os.environ.get("NAUTILUS_PROJECT_ROOT")
    if PROJECT_ROOT is None:
        logger.error("NAUTILUS_PROJECT_ROOT environment variable is not set.")
        raise EnvironmentError(
            "NAUTILUS_PROJECT_ROOT environment variable is not set.")
    PROJECT_ROOT = pathlib.Path(PROJECT_ROOT)

    dotenv.load_dotenv(PROJECT_ROOT / "docker" / ".env", override=True)
    CATALOG_PATH = str(PROJECT_ROOT / os.environ["CATALOG_PATH"])

    best_params = optimize_strategy()
    logger.info("Done.")
