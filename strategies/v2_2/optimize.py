import os
import pathlib
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from omegaconf import OmegaConf
from hydra import initialize, compose
from hydra.core.config_store import ConfigStore
from hydra import initialize, compose

from hydra.core.global_hydra import GlobalHydra


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
sys.path.append(str(pathlib.Path(__file__).resolve().parent))

from nautilus_trader.common.component import init_logging, Logger

guard = init_logging()
logger = Logger("MyCoolLogger")

logger.info("Optimization script started")

from base import PUT101StrategyConfig, MainConfig

@dataclass
class BacktestConfig:
    study_name: str = "bt_default_experiment" + "_1"
    storage: str = "sqlite:///./optuna.db"
    version:str = os.path.basename(pathlib.Path(__file__).parent)
    n_trials: int = 2
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
            logging=LoggingConfig(log_level="ERROR", 
                                  log_level_file="DEBUG", 
                                  print_config=True,
                                  log_colors=True,
                                  log_file_format="json",
                                  log_directory=f"{config.project_root}/logs",
                                  log_file_name=f"{config.study_name}_trial_{trial.number}.json",
                                  log_component_levels={
                                      f'OrderMatchingEngine({venue.value})' : 'WARN',
                                    },
                                  bypass_logging=False,
                                  ),
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


def objective(trial: optuna.Trial, config: BacktestConfig) -> list[float]:
    """Objective function for optimization."""
    from time import sleep
    
    run_config = create_backtest_config(trial, config)
    node = BacktestNode([run_config])
    

    print(f"Running trial {trial.number}")
    
    try:
        results = node.run(raise_exception=True)
        res: BacktestResult = results[0]
        logger.info(f"Trial {trial.number} completed: {res}")        
        metrics = metrics_from_result(res)
        
        return [metrics[m] for m,_ in config.optimization_goals]

    except Exception as e:
        logger.error(f"Trial failed: {e}")
        raise e
    finally:
        logger.info(f"disposing backtest node")
        node.dispose()
        del node


def run_optimization(cfg: BacktestConfig) -> None:
    """Run optimization using Optuna."""
    study = optuna.create_study(
        study_name=cfg.study_name, directions=[ d for n,d in cfg.optimization_goals], 
        storage=cfg.storage,
        load_if_exists=True
    )
    study.optimize(lambda t: objective(t, cfg), n_trials=cfg.n_trials)
    logger.info(f"Best trials: {study.best_trials}")
    
    for t in study.best_trials:
        logger.info(f"Trial {t.number} - {t.values}")
        logger.info(f"Trial {t.number} - {t.params}")
        logger.info(f"Trial {t.number} - {t.user_attrs}")


def metrics_from_result(res: BacktestResult) -> Dict[str, Any]:
    """
    is a dataclass
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
    metrics = res.__dict__
    metrics.update(res.stats_pnls["USD"])
    metrics.update(res.stats_returns)
        
    return metrics

if __name__ == "__main__":
    dotenv.load_dotenv(verbose=True, override=True)
    PROJECT_ROOT = pathlib.Path(os.environ["NAUTILUS_PROJECT_ROOT"])
    logger.debug(f"Project root: {PROJECT_ROOT}")
    dotenv.load_dotenv(PROJECT_ROOT / "docker" / ".env", override=True)
    CATALOG_PATH = str(PROJECT_ROOT / os.environ["CATALOG_PATH"])
    logger.debug(f"Catalog path: {CATALOG_PATH}")
    

    validate_environment(["NAUTILUS_PROJECT_ROOT"])

    initialize(config_path=None)
    cfg: BacktestConfig = compose(config_name="backtest_config", overrides=[
        f"project_root={PROJECT_ROOT}",
        f"catalog_path={CATALOG_PATH}",
    ])
    cfg.optimization_goals = [("PnL% (total)", "maximize"), ("Win Rate", "maximize")]
    
    logger.info(f"Loaded configuration: {OmegaConf.to_yaml(cfg)}")

    run_optimization(cfg)
