import MetaTrader5 as mt
import numpy as np
from datetime import datetime
import pandas as pd
import numpy as np
from datetime import datetime, date
import os

from nautilus_trader.model.currency import Currency
from nautilus_trader.model.data import BarType, Bar
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider


class utils:
    @staticmethod
    def print_bytes(n_bytes: int, use_iec_binary=True):
        # print the bytes in a human-readable format
        # according to this table: https://en.wikipedia.org/wiki/Byte#Multiple-byte_units

        if use_iec_binary:
            units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
            base = 1024
        else:
            units = ["B", "KB", "MB", "GB", "TB", "PB"]
            base = 1000

        for unit in units:
            if n_bytes < base:
                print(f"{n_bytes:.1f} {unit}")
                return
            n_bytes /= base


class CSV_MT5BarDataLoader:
    @staticmethod
    def load(file_path: os.PathLike[str] | str) -> pd.DataFrame:
        df = pd.read_csv(
            file_path,
            index_col="time",
            parse_dates=True,
        )
        df.index = pd.to_datetime(df.index, format="mixed")
        return df

class MTLoginConfig:
    def __init__(self, server: str, login: int, password: str):
        self.server = server
        self.login = login
        self.password = password


def init(config: MTLoginConfig = None) -> bool:
    mt.initialize()
    if config:
        mt.login(config.login, config.password, config.server)
    return mt.terminal_info().update_time > 0


def is_init() -> bool:
    return mt.terminal_info().update_time > 0


class MT5Loader:
    def __init__(self, data_path: str, catalog_path: str, config: MTLoginConfig = None, load_id: int = 0):
        self.config = config
        self.data_path = data_path
        self.catalog_path = catalog_path
        self.venue = Venue(f"SIM-{self.config.server}")
        self.catalog = ParquetDataCatalog(self.catalog_path)

    def delete_parquet_files(self, symbol: str, timeframe: int, parts: list[int] = None):
        # delete all parquet files for the specified symbol and timeframe and parts
        # if parts is None, delete all parts

        # delete catalog dir
        if os.path.exists(self.catalog_path):
            instrument_path = os.path.join(self.catalog_path, f"{symbol}.{self.venue.value}-{timeframe}-LAST-EXTERNAL")
            print(f"INFO: Deleting instrument at: {instrument_path}")
            os.remove(instrument_path)

        pass

    def load(self, symbol: str, timeframe: int, start: datetime) -> bool:


        pass

    def get_catalog(self):
        return self.catalog

    def load_csv_to_catalog(self, symbol: str, timeframe: int, start: datetime, end: datetime) -> (Currency, BarType):
        # create catalog directory if it doesn't exist
        if not os.path.exists(self.catalog_path):
            print(f"INFO: Creating catalog directory at: {self.catalog_path}")
            os.mkdir(self.catalog_path)

        instrument = TestInstrumentProvider.default_fx_ccy(symbol, self.venue)
        ticker_path = os.path.join(self.data_path, ticker.replace('/', '') + ".csv")
        df = CSV_MT5BarDataLoader.load(ticker_path)

        bar_type = BarType.from_str(ticker + f".{self.venue.value}-{timeframe}-LAST-EXTERNAL")  # arbitrary? but .SIM-*** and meaningful name
        wrangler = BarDataWrangler(bar_type, instrument)
        bars: list[Bar] = wrangler.process(df)

        # instrument also has to be written in order to access data for the instrument
        self.catalog.write_data([instrument], "part-{i}")
        self.catalog.write_data(bars, basename_template="part-{i}")

    @staticmethod
    def _load_rates(symbol: str, timeframe: int, dt_from: datetime, dt_to: datetime, ) -> np.ndarray:
        rates = mt.copy_rates_range(symbol, timeframe, dt_from, dt_to)
        return rates

    @staticmethod
    def _load_symbol_to_frame(symbol: str, timeframe: int, date_from: datetime, date_to: datetime) -> (pd.DataFrame):
        rates: np.ndarray = MT5Loader._load_rates(symbol, mt.TIMEFRAME_D1, date_from, date_to)

        # Prepare Dataframe
        rates: pd.DataFrame = pd.DataFrame(rates)
        rates['time'] = pd.to_datetime(rates['time'], unit='s')
        rates.set_index('time', inplace=True)
        return rates

    @staticmethod
    def _load_symbol_rates_to_csv(symbol, timeframe, start, end, data_path: str) -> bool:
        # load data from the MetaTrader 5 terminal into parquet files for further backtesting

        if not is_init():
            print("Error: MT5 terminal not initialized")
            return False
        rates = MT5Loader._load_symbol_to_frame(symbol, timeframe, start, end)
        csv_path = os.path.join(data_path, ticker.replace('/', '') + ".csv")
        rates.to_csv(csv_path)
        return True



    def __enter__(self):
        init(self.config)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        mt.shutdown()








# Load all tickers into catalog
for ticker in tickers:


catalog.instruments()