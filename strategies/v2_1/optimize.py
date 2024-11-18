import os
import pathlib
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from omegaconf import OmegaConf
from hydra import initialize, compose
from hydra.core.config_store import ConfigStore
import pandas as pd
import optuna
import dotenv
import numpy as np
from nautilus_trader.trading.strategy import ImportableStrategyConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.config import (
    BacktestVenueConfig,
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestEngineConfig,
    RiskEngineConfig,
    LoggingConfig,
)
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from dataclasses import dataclass
from typing import List, Tuple
from omegaconf import MISSING

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

logger.info("Optimization script started")

from .base import PUT101StrategyConfig, MainConfig

@dataclass
class BacktestConfig:
    study_name: str = "bt_default_experiment" + "_0"
    version:str = os.path.basename(pathlib.Path(__file__).parent)
    n_trials: int = 1
    project_root: str = os.environ.get("NAUTILUS_PROJECT_ROOT", MISSING)
    catalog_path: str = f"{project_root}/data/catalog"
    optimization_goals: list = field(default_factory=list) # list[tuple[str,str]] metric name, metric optim direction

# Register configuration schema
cs = ConfigStore.instance()
#cs.store(name="strategy_config", node=)
cs.store(name="backtest_config", node=BacktestConfig)


def validate_environment(env_vars: List[str]) -> None:
    """Validate required environment variables."""
    missing_vars = [var for var in env_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise EnvironmentError(f"Set the following environment variables: {missing_vars}")


def create_backtest_config(trial: optuna.Trial, config: BacktestConfig) -> BacktestRunConfig:
    """Create a backtest configuration for a specific trial."""
    bb_period = trial.suggest_int("bb_period", 10, 50)
    bb_std = trial.suggest_float("bb_std", 1.0, 3.0)
    tp_pips = trial.suggest_int("tp_pips", 0, 50)
    sl_pips = trial.suggest_int("sl_pips", 5, 100)
    risk_reward = trial.suggest_float("risk_reward", 0.1, 10.0)
        
    venue = Venue("SIM_EIGHTCAP")
    symbol = Symbol("EURUSD")
    instrument_id = InstrumentId(symbol, venue)
    start = dt_to_unix_nanos(pd.Timestamp("2020-01-01"))
    end = start + pd.Timedelta(days=3).value

    
    main_conf = MainConfig(
        environment=os.environ.copy(),
        instrument_id=instrument_id.value,
        bar_type=f"{instrument_id}-5-MINUTE-BID-INTERNAL",
        IDENTIFIER=f"{config.study_name}_trial_{trial.number}",
        bb_params=[
            (bb_period, bb_std),
        ],
        sl_pips=sl_pips,
        tp_pips=tp_pips,
        risk_reward=risk_reward,
    )
    
    dict_conf = dict(
        main=main_conf,
    )
    

    return BacktestRunConfig(
        engine=BacktestEngineConfig(
            trader_id=f"BACKTESTER-{trial.number:03d}",
            strategies=[
                ImportableStrategyConfig(
                    config_path=f"{config.version}.base:PUT101StrategyConfig",
                    strategy_path=f"{config.version}.base:PUT101Strategy",
                    config=dict_conf,
                )
            ],
            risk_engine=RiskEngineConfig(bypass=True),
            logging=LoggingConfig(log_level="WARN", log_level_file="DEBUG"),
        ),
        data=[
            BacktestDataConfig(
                catalog_path=config.catalog_path,
                data_cls=QuoteTick,
                instrument_id=instrument_id,
                start_time=start,
                end_time=end,
            )
        ],
        venues=[
            BacktestVenueConfig(
                name=venue.value,
                account_type="MARGIN",
                oms_type="HEDGING",
                default_leverage=500,
                base_currency="USD",
                starting_balances=["10000 USD"],
            )
        ],
    )


def objective(trial: optuna.Trial, config: BacktestConfig) -> float:
    """Objective function for optimization."""
    from time import sleep
    
    run_config = create_backtest_config(trial, config)
    node = BacktestNode([run_config])

    print(f"Running trial {trial.number}")
    sleep(2)
    
    try:
        results = node.run(raise_exception=True)
        res: BacktestResult = results[0]
        logger.info(f"Trial {trial.number} completed: {res.stats_pnls}")
        print(f"Trial {trial.number} completed: {res.stats_pnls}")
        print(f"DONE")
        metrics = res.stats_pnls['USD']['Profit Factor']  # Example metric
        return metrics
    except Exception as e:
        logger.error(f"Trial failed: {e}")
        raise e
    finally:
        logger.info(f"disposing backtest node")
        node.dispose()


def run_optimization(cfg: BacktestConfig) -> None:
    """Run optimization using Optuna."""
    study = optuna.create_study(
        study_name=cfg.study_name, directions=["maximize"], load_if_exists=True
    )
    study.optimize(lambda t: objective(t, cfg), n_trials=cfg.n_trials)
    logger.info(f"Best trial: {study.best_trial}")


if __name__ == "__main__":
    dotenv.load_dotenv(verbose=True, override=True)
    PROJECT_ROOT = pathlib.Path(os.environ["NAUTILUS_PROJECT_ROOT"])
    logger.debug(f"Project root: {PROJECT_ROOT}")
    dotenv.load_dotenv(PROJECT_ROOT / "docker" / ".env", override=True)
    CATALOG_PATH = str(PROJECT_ROOT / os.environ["CATALOG_PATH"])
    logger.debug(f"Catalog path: {CATALOG_PATH}")
    

    validate_environment(["NAUTILUS_PROJECT_ROOT"])

    initialize(config_path=None)
    cfg = compose(config_name="backtest_config", overrides=[
        f"project_root={PROJECT_ROOT}",
        f"catalog_path={CATALOG_PATH}",
    ])
    logger.info(f"Loaded configuration: {OmegaConf.to_yaml(cfg)}")

    run_optimization(cfg)
