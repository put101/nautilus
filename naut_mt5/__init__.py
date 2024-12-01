from typing import Callable, Optional

import MetaTrader5 as mt
import numpy as np
from datetime import datetime
import pandas as pd
import numpy as np
from datetime import datetime, date
import os

from nautilus_trader.model.data import BarType, Bar
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

class MTLoginConfig:
    def __init__(self, server: str, login: int, password: str):
        self.server = server
        self.login = login
        self.password = password


class MT5Loader:
    def __init__(self, data_path: str, catalog_path: str, config: MTLoginConfig = None, venue: str = None):
        self.config = config
        self.data_path = data_path
        self.catalog_path = catalog_path
        if venue is not None:
            self.venue = Venue(venue)
        else:
            self.venue = Venue(f"SIM-{self.config.server}")
        self.catalog = ParquetDataCatalog(self.catalog_path)

    @staticmethod
    def server_venue_first_word(server: str) -> str:
        return server.strip().split(" ")[0]

    def init(self) -> bool:
        config = self.config

        mt.initialize()
        if config:
            mt.login(config.login, config.password, config.server)
        info: mt.TerminalInfo = mt.terminal_info()
        if info is None or not info.connected:
            return False
        return True

    def get_venue(self) -> Venue:
        return self.venue

    def get_catalog(self) -> ParquetDataCatalog:
        return self.catalog

    """
    TIMEFRAME_M1                        = 1
    TIMEFRAME_M2                        = 2
    TIMEFRAME_M3                        = 3
    TIMEFRAME_M4                        = 4
    TIMEFRAME_M5                        = 5
    TIMEFRAME_M6                        = 6
    TIMEFRAME_M10                       = 10
    TIMEFRAME_M12                       = 12
    TIMEFRAME_M15                       = 15
    TIMEFRAME_M20                       = 20
    TIMEFRAME_M30                       = 30
    TIMEFRAME_H1                        = 1  | 0x4000
    TIMEFRAME_H2                        = 2  | 0x4000
    TIMEFRAME_H4                        = 4  | 0x4000
    TIMEFRAME_H3                        = 3  | 0x4000
    TIMEFRAME_H6                        = 6  | 0x4000
    TIMEFRAME_H8                        = 8  | 0x4000
    TIMEFRAME_H12                       = 12 | 0x4000
    TIMEFRAME_D1                        = 24 | 0x4000
    TIMEFRAME_W1                        = 1  | 0x8000
    TIMEFRAME_MN1                       = 1  | 0xC000
    """
    @staticmethod
    def get_timeframe_nautilus_str(mt_timeframe: int) -> str:
        if mt_timeframe == 1:
            return "1-MINUTE"
        if mt_timeframe == 3:
            return "3-MINUTE"
        if mt_timeframe == 4:
            return "4-MINUTE"
        if mt_timeframe == 5:
            return "5-MINUTE"
        if mt_timeframe == 6:
            return "6-MINUTE"
        if mt_timeframe == 10:
            return "10-MINUTE"
        if mt_timeframe == 12:
            return "12-MINUTE"
        if mt_timeframe == 15:
            return "15-MINUTE"
        if mt_timeframe == 20:
            return "20-MINUTE"
        if mt_timeframe == 30:
            return "30-MINUTE"
        if mt_timeframe == 1 | 0x4000:
            return "1-HOUR"
        if mt_timeframe == 2 | 0x4000:
            return "2-HOUR"
        if mt_timeframe == 4 | 0x4000:
            return "4-HOUR"
        if mt_timeframe == 3 | 0x4000:
            return "3-HOUR"
        if mt_timeframe == 6 | 0x4000:
            return "6-HOUR"
        if mt_timeframe == 8 | 0x4000:
            return "8-HOUR"
        if mt_timeframe == 12 | 0x4000:
            return "12-HOUR"
        if mt_timeframe == 24 | 0x4000:
            return "1-DAY"
        if mt_timeframe == 1 | 0x8000:
            return "1-WEEK"
        if mt_timeframe == 1 | 0xC000:
            return "1-MONTH"
        raise ValueError(f"Unknown timeframe: {mt_timeframe}")


    # "AUD/USD.SIM-1-MINUTE-MID-INTERNAL",
    def get_bar_type(self, symbol: str, timeframe: int) -> BarType:
        return BarType.from_str(symbol + f".{self.get_venue().value}-{self.get_timeframe_nautilus_str(timeframe)}-LAST-EXTERNAL")

    # NOTE: Works only with one stringt for both the symbol and the ticker
    # TODO: add support for arbitrary symbols like "EURUSD.i" and "EURUSD_raw"

    def get_instrument_FOREX(self, symbol: str) -> CurrencyPair:
        return TestInstrumentProvider.default_fx_ccy(symbol, self.venue)

    def get_instrument_METAL(self, symbol: str) -> CurrencyPair:
        raise NotImplementedError("#not implemented, check mt5 differences for metals")

    def get_instrument_CFD(self, symbol: str) -> CurrencyPair:
        raise NotImplementedError("not implemented, check mt5 differences for CFDs (indices, stocks, etc.)")

    def load_csv_to_catalog(self, symbol_csv: str, symbol_catalog: str, timeframe: int, start: datetime, end: datetime) -> bool:

        # create catalog directory if it doesn't exist
        if not os.path.exists(self.catalog_path):
            print(f"INFO: Creating catalog directory at: {self.catalog_path}")
            os.mkdir(self.catalog_path)

        instrument = TestInstrumentProvider.default_fx_ccy(symbol_catalog, self.venue)
        csv_path = MT5Loader.get_csv_path(symbol_csv, timeframe, start, end, self.data_path)
        df = pd.read_csv(csv_path, index_col="time", parse_dates=True)
        bar_type = self.get_bar_type(symbol=symbol_catalog, timeframe=timeframe)
        wrangler = BarDataWrangler(bar_type, instrument)
        bars: list[Bar] = wrangler.process(df)

        # instrument also has to be written in order to access data for the instrument
        basename_template = "part-{i}" + f"-from-{int(start.timestamp())}-to-{int(end.timestamp())}"
        self.catalog.write_data([instrument], basename_template)
        self.catalog.write_data(bars, basename_template)
        return True

    @staticmethod
    def copy_rates_range(symbol: str, timeframe: int, dt_from: datetime, dt_to: datetime, ) -> np.ndarray:
        rates = mt.copy_rates_range(symbol, timeframe, dt_from, dt_to)
        return rates

    @staticmethod
    def load_symbol_to_frame(symbol_broker: str, timeframe: int, date_from: datetime, date_to: datetime) -> Optional[pd.DataFrame]:
        rates: np.ndarray = MT5Loader.copy_rates_range(symbol_broker, timeframe, date_from, date_to)
        if rates is None:
            print(f"ERROR: Failed to copy rates: {symbol_broker} {timeframe} {date_from} {date_to}")
            return None

        rates: pd.DataFrame = pd.DataFrame(rates)
        rates['time'] = pd.to_datetime(rates['time'], unit='s')
        rates.set_index('time', inplace=True)
        return rates

    @staticmethod
    def get_csv_path(symbol_broker: str, timeframe: int, start, end, data_path: str) -> str:
        csv_path = os.path.join(data_path, symbol_broker + "_" + MT5Loader.get_timeframe_nautilus_str(timeframe) \
                                + "_" + str(int(start.timestamp())) + "_" + str(int(end.timestamp())) + ".csv")
        return csv_path
    @staticmethod
    def load_symbol_rates_to_csv(symbol_broker: str, symbol_csv: str, timeframe, start, end, data_path: str) -> bool:
        # load data from the MetaTrader 5 terminal into parquet files for further backtesting
        rates = MT5Loader.load_symbol_to_frame(symbol_broker, timeframe, start, end)
        if rates is None:
            return False
        csv_path = MT5Loader.get_csv_path(symbol_broker, timeframe, start, end, data_path)
        rates.to_csv(csv_path)
        print(f"INFO: Saved rates to csv: {csv_path}")
        return True
