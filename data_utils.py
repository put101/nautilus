import os
from nautilus_trader.data.engine import ParquetDataCatalog
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.data import BarType, Bar
import pandas as pd
from pandas import DataFrame

from nautilus_trader.persistence.wranglers import BarDataWrangler

# this file should be able to handle mt5 stuff without a dependency to mt5

def buy_or_sell(flag):
    '''
    see https://www.mql5.com/en/forum/75268
    for explanation on MetaTrader flags
    '''
    if (flag & 32) and (flag & 64):
        return 'both'
    elif flag & 32:
        return 'buy'
    elif flag & 64:
        return 'sell'

# delete a bar_type from catalog by deleting folder with its parquet part files\n",
def delete_parquet_data(bar_type: BarType, catalog: str) -> bool:
    import shutil
    try:
        bar_type_directory: str = os.path.join(catalog, 'data', 'bar', bar_type_to_str(bar_type))
        shutil.rmtree(bar_type_directory)
    except Exception as e:
        print(e)
        return False
    return True


def load_mt5_csv_dataframe(file_path: os.PathLike[str] | str) -> DataFrame:
    df = pd.read_csv(
        file_path,
        index_col="time",
        parse_dates=True,
    )
    df.index = pd.to_datetime(df.index, format="mixed")
    return df

def load_df_bars(df: DataFrame, bar_type: BarType, instrument: Instrument) -> list[Bar]:
    wrangler = BarDataWrangler(bar_type, instrument)
    bars: list[Bar] = wrangler.process(df)
    return bars

def bar_type_to_str(bar_type: BarType) -> str:
    agg_src_mapping = {
        1: 'EXTERNAL',
        2: 'INTERNAL'
    }
    return f"{bar_type.instrument_id}-{bar_type.spec}-{agg_src_mapping[bar_type.aggregation_source]}"

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



