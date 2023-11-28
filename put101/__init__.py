from typing import Callable

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
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# Can be given to BarDataWrangler for processing
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

    def delete_catalog_parquet_files(self, symbol: str, timeframe: int, parts: list[int] = None):
        # delete all parquet files for the specified symbol and timeframe by deleting the types directory

        # delete catalog dir
        if os.path.exists(self.catalog_path):
            instrument_path = os.path.join(self.catalog_path, f"{symbol}.{self.venue.value}-{timeframe}M-LAST-EXTERNAL")
            print(f"INFO: Deleting instrument at: {instrument_path}")

            try:
                os.removedirs(instrument_path)
            except FileNotFoundError as error:
                print(f"ERROR: {error}")
        pass


    # "AUD/USD.SIM-1-MINUTE-MID-INTERNAL",
    def get_bar_type(self, symbol: str, timeframe: int) -> BarType:
        return BarType.from_str(symbol + f".{self.get_venue().value}-{timeframe}-MINUTE-MID-INTERNAL")


    def load(self, symbol: str, timeframe: int, start: datetime) -> bool:
        # mt5 -> csv -> catalog
        self.load_symbol_rates_to_csv(symbol, timeframe, start, datetime.now(), self.data_path)
        self.load_csv_to_catalog(symbol, timeframe)
        pass



    # NOTE: Works only with one stringt for both the symbol and the ticker
    # TODO: add support for arbitrary symbols like "EURUSD.i" and "EURUSD_raw"

    def get_instrument_FOREX(self, symbol: str) -> CurrencyPair:
        return TestInstrumentProvider.default_fx_ccy(symbol, self.venue)

    def get_instrument_METAL(self, symbol: str) -> CurrencyPair:
        raise NotImplementedError("#not implemented, check mt5 differences for metals")

    def get_instrument_CFD(self, symbol: str) -> CurrencyPair:
        raise NotImplementedError("not implemented, check mt5 differences for CFDs (indices, stocks, etc.)")

    def load_csv_to_catalog(self, symbol: str, timeframe: int):
        # create catalog directory if it doesn't exist
        if not os.path.exists(self.catalog_path):
            print(f"INFO: Creating catalog directory at: {self.catalog_path}")
            os.mkdir(self.catalog_path)

        instrument = TestInstrumentProvider.default_fx_ccy(symbol, self.venue)
        ticker_path = os.path.join(self.data_path, symbol.replace('/', '') + ".csv")
        df = CSV_MT5BarDataLoader.load(ticker_path)

        bar_type = self.get_bar_type(symbol=symbol, timeframe=timeframe)  # arbitrary? but .SIM-*** and meaningful name
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
    def load_symbol_to_frame(symbol: str, timeframe: int, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        rates: np.ndarray = MT5Loader._load_rates(symbol, mt.TIMEFRAME_D1, date_from, date_to)

        # Prepare Dataframe
        rates: pd.DataFrame = pd.DataFrame(rates)
        rates['time'] = pd.to_datetime(rates['time'], unit='s')
        rates.set_index('time', inplace=True)
        return rates

    @staticmethod
    def load_symbol_rates_to_csv(symbol, timeframe, start, end, data_path: str):
        # load data from the MetaTrader 5 terminal into parquet files for further backtesting
        rates: pd.DataFrame = MT5Loader.load_symbol_to_frame(symbol, timeframe, start, end)
        csv_path = os.path.join(data_path, symbol.replace('/', '') + ".csv")
        rates.to_csv(csv_path)

