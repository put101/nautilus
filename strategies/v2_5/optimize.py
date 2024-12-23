import os
import pathlib
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from omegaconf import DictConfig, OmegaConf
from hydra import initialize, compose
from hydra.utils import instantiate, get_class
from hydra.core.config_store import ConfigStore
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
from nautilus_trader.model.data import QuoteTick, Bar
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from dataclasses import dataclass
from typing import List, Tuple
from omegaconf import MISSING
import pathlib
import sys
import dotenv
dotenv.load_dotenv(verbose=True, override=True)

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

from nautilus_trader.common.component import init_logging, Logger

guard = init_logging()
logger = Logger("MyCoolLogger")

logger.info("Optimization script started")

from base import PUT101StrategyConfig, MainConfig

@dataclass
class BacktestConfig:
    project_root: str
    catalog_path: str
    n_trials: int
    study_name: str # "bt_default_experiment" + "_1"
    storage: str # sqlite:///example.db
    start_dt: str
    end_dt: str
    version: str = os.path.basename(pathlib.Path(__file__).parent)
    venue: str = "SIM"
    symbol: str = "XAUUSD"
    data_cls: str = "QuoteTick" # Bar, QuoteTick
    optimization_goals: list = field(default_factory=list) # list[tuple[str,str]] metric name, metric optim direction

cs = ConfigStore.instance()
cs.store(name="config", node=BacktestConfig)

def validate_environment(env_vars: List[str]) -> None:
    """Validate required environment variables."""
    missing_vars = [var for var in env_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise EnvironmentError(f"Set the following environment variables: {missing_vars}")


def generate_indicator_configs(trial: optuna.Trial) -> list[dict]:
    """Generate a list of indicator configurations."""
    indicator_classes = [
        "nautilus_trader.indicators.bollinger_bands.BollingerBands",
        "nautilus_trader.indicators.rsi.RelativeStrengthIndex",
        # Add more indicator classes as needed
    ]
    
    indicator_configs = []
    num_indicators = trial.suggest_int("num_indicators", 1, len(indicator_classes))
    
    for i in range(num_indicators):
        indicator_class = trial.suggest_categorical(f"indicator_class_{i}", indicator_classes)
        if indicator_class == "nautilus_trader.indicators.bollinger_bands.BollingerBands":
            period = trial.suggest_int(f"bb_period_{i}", 10, 50)
            std = trial.suggest_float(f"bb_std_{i}", 1.0, 3.0)
            params = [period, std]
        elif indicator_class == "nautilus_trader.indicators.rsi.RelativeStrengthIndex":
            period = trial.suggest_int(f"rsi_period_{i}", 10, 50)
            params = [period]
        # Add more indicator parameter configurations as needed
        indicator_configs.append({"class": indicator_class, "params": params})
    
    return indicator_configs


def create_backtest_config(trial: optuna.Trial, cfg: BacktestConfig) -> BacktestRunConfig:
    """Create a backtest configuration for a specific trial."""
    
    scfg = compose(config_name="strategy")
    
    bb_period = trial.suggest_int("bb_period", scfg.bb_period_min, scfg.bb_period_max)
    
    bb_std = trial.suggest_float("bb_std", 1.0, 3.0)
    #tp_pips = trial.suggest_int("tp_pips", 0, 50)
    sl_pips = trial.suggest_int("sl_pips", 5, 100)
    risk_reward = trial.suggest_float("risk_reward", 0.1, 10.0)
        
    venue = Venue(cfg.venue)
    symbol = Symbol(cfg.symbol)
    instrument_id = InstrumentId(symbol, venue)
    start = dt_to_unix_nanos(pd.Timestamp(cfg.start_dt))
    end = dt_to_unix_nanos(pd.Timestamp(cfg.end_dt))
    if cfg.end_dt is None:
        end = start + pd.Timedelta(days=cfg.end_days).value

    IDENTIFIER=f"{cfg.study_name}_trial_{trial.number}"
    trial.set_user_attr("IDENTIFIER", IDENTIFIER)

    indicator_configs = generate_indicator_configs(trial)
    
    main_conf = MainConfig(
        environment=os.environ.copy(),
        instrument_id=instrument_id,
        bar_type=f"{instrument_id}-5-MINUTE-BID-INTERNAL",
        IDENTIFIER=f"{cfg.study_name}_trial_{trial.number}",
        indicators=indicator_configs,
        sl_pips=sl_pips,
        tp_pips=0,
        risk_reward=risk_reward,
        bb_params=[(bb_period, bb_std)],
        rsi_periods=[]
    )
    
    dict_conf = dict(
        main=main_conf,
    )
    
    btconf= BacktestRunConfig(
        engine=BacktestEngineConfig(
            trader_id=f"BACKTESTER-{trial.number:03d}",
            strategies=[
                ImportableStrategyConfig(
                    config_path=f"{cfg.version}.base:PUT101StrategyConfig",
                    strategy_path=f"{cfg.version}.base:PUT101Strategy",
                    config=dict_conf,
                )
            ],
            risk_engine=RiskEngineConfig(bypass=True),
            logging=LoggingConfig(log_level="ERROR", 
                                  log_level_file="DEBUG", 
                                  print_config=True,
                                  log_colors=True,
                                  log_file_format="json",
                                  log_directory=f"{cfg.project_root}/logs",
                                  log_file_name=f"{cfg.study_name}_trial_{trial.number}.json",
                                  log_component_levels={
                                      f'OrderMatchingEngine({venue.value})' : 'WARN',
                                    },
                                  bypass_logging=False,
                                  ),
        ),
        data=[
            #BacktestDataConfig(
            #   catalog_path=config.catalog_path,
            #    data_cls=QuoteTick,
            #    instrument_id=instrument_id,
            #    start_time=start,
            #    end_time=end,
            #),
            BacktestDataConfig(
                catalog_path=cfg.catalog_path,
                data_cls=get_class(cfg.data_cls),
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
    logger.info(f"Created backtest config: ${str(btconf)}") 
    
    return btconf


def objective(trial: optuna.Trial, config: BacktestConfig) -> list[float]:
    """Objective function for optimization."""
    from time import sleep
    
    run_config = create_backtest_config(trial, config)
    trial.set_user_attr("config", OmegaConf.to_yaml(config))
    trial.set_user_attr("run_config", str(run_config))
    node = BacktestNode([run_config])
    print(f"Running trial {trial.number}")
    
    try:
        results = node.run(raise_exception=True)
        res: BacktestResult = results[0]
        logger.info(f"Trial {trial.number} completed: {res}")        
        flattened_results = metrics_from_result(res)

        # add additional metrics
        trial.set_user_attr("metrics", flattened_results)       
        
        return [flattened_results[m] for m,_ in config.optimization_goals]

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
    dotenv.load_dotenv(verbose=True, dotenv_path=pathlib.Path(os.environ['NAUTILUS_PROJECT_ROOT']) / "docker" / ".env", override=True)

    validate_environment(["NAUTILUS_PROJECT_ROOT"])

    initialize(version_base=None, config_path="conf")

    cfg = compose(config_name="optimize", 
                                  overrides=[
                                      f'version={os.path.basename(pathlib.Path(__file__).parent)}',
                                  ])
    
    cfg = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
    logger.info(f"Optimization config: {cfg}")
    cfg = instantiate(cfg)
    logger.info(f"Instantiated Optimization config: {cfg}")

    run_optimization(cfg)
