import os
from nautilus_trader.data.engine import ParquetDataCatalog
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.data.bar import BarType, Bar
import pandas as pd
from pandas import DataFrame

from nautilus_trader.persistence.wranglers import BarDataWrangler

# this file should be able to handle mt5 stuff without a dependency to mt5

eurusd_daily_str = "EURUSD.SIM-1-DAY-BID-EXTERNAL"

def load_mt5_csv_dataframe(file_path: os.PathLike[str] | str) -> DataFrame:
    df = pd.read_csv(
        file_path,
        index_col="time",
        parse_dates=True,
    )
    df.index = pd.to_datetime(df.index, format="mixed")
    return df

def load_df_bars(catalog: ParquetDataCatalog, df: DataFrame, bar_type: BarType, instrument: Instrument) -> list[Bar]:
    wrangler = BarDataWrangler(bar_type, instrument)
    bars: list[Bar] = wrangler.process(df)
    return bars

def bar_type_to_str(bar_type: BarType) -> str:
    agg_src_mapping = {
        1: 'EXTERNAL',
        2: 'INTERNAL'
    }
    return f"{bar_type.instrument_id}-{bar_type.spec}-{agg_src_mapping[bar_type.aggregation_source]}"



