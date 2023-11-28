# make a notebnook out of this


import logging
from datetime import datetime

# load data from the MetaTrader 5 terminal into parquet files for further backtesting
import put101 as p
import dotenv
import os
import MetaTrader5 as mt5

if not dotenv.load_dotenv():
    logging.log(logging.INFO, "No .env file found")

MT5_SERVER = os.environ["MT5_SERVER"]
MT5_LOGIN = os.environ["MT5_LOGIN"]
MT5_PASSWORD = os.environ["MT5_PASSWORD"]
DATA_PATH = os.environ["DATA_PATH"]
CATALOG_PATH = os.environ["CATALOG_PATH"]

loader_config = p.MTLoginConfig(server=MT5_SERVER, login=MT5_LOGIN, password=MT5_PASSWORD)

loader = p.MT5Loader(data_path=DATA_PATH, catalog_path=CATALOG_PATH, config=loader_config)

# load a couple of symbols into the catalog using the loader
symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
timeframes = [mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H4, mt5.TIMEFRAME_D1]
start_date = datetime(2020, 1, 1)



for symbol in symbols:
    for timeframe in timeframes:
        loader.delete_catalog_parquet_files(symbol=symbol, timeframe=mt5.TIMEFRAME_M1)
        loader.load(symbol=symbol, timeframe=timeframe, start=start_date)
        bar_type = loader.get_bar_type(symbol=symbol, timeframe=timeframe)
        instrument = loader.get_instrument_FOREX(symbol=symbol)
        print(f"INFO: Loaded {instrument} {bar_type} into catalog")

if __name__ == "__main__":
    pass