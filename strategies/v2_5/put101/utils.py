# nautilus
from enum import Enum

import pandas as pd
from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.accounting.accounts.margin import MarginAccount
from nautilus_trader.config import (
    BacktestRunConfig,
    BacktestEngineConfig,
    BacktestVenueConfig,
)
from nautilus_trader.core.datetime import maybe_unix_nanos_to_dt
from nautilus_trader.core.rust.model import (
    PositionSide,
    OrderSide,
    TimeInForce,
    OrderType,
)
from nautilus_trader.model.data import Bar
from nautilus_trader.model.objects import Currency, Money, Quantity
from nautilus_trader.model.orders import OrderList
from nautilus_trader.model.position import Position
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.indicators.base.indicator import Indicator

from bokeh.layouts import layout, column, row
from bokeh.plotting import figure

# others
from datetime import timedelta
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from nautilus_trader.portfolio import Portfolio
from pandas import Timestamp
from decimal import Decimal

# deprecated
#  ----------
from .indicators import TrackerFloat, TrackerMulti
from . import vizz
from .vizz import Styling, LineIndicatorStyle


def in_session_hours(sessions: list[tuple[int, int]], ts: pd.Timestamp):
    for start, end in sessions:
        if start <= ts.hour < end:
            return True
    return False


class RiskCalculator:
    @staticmethod
    def qty_from_risk(
        risk: float, entry: float, exit: float, ins: Instrument
    ) -> Quantity:
        risk_points = abs(entry - exit) / ins.price_increment
        point_value_per_unit = float(ins.price_increment) * float(ins.lot_size)
        lots = (risk / risk_points) * (1 / point_value_per_unit)
        qty = lots * ins.lot_size
        return ins.make_qty(qty)


def get_configs():
    pass



def get_layout(
    res: BacktestResult,
    script_name: str,
    bars: list[Bar],
    overlay_indicators: list[TrackerMulti],
    overlay_indicator_styles: list[Styling],
    extra_plots: list[tuple[list[TrackerMulti], list[Styling]]],
    positions: list[Position],
):

    # add all wheel zoom
    tools = "pan,xwheel_zoom,ywheel_zoom,wheel_zoom,box_zoom,reset,save"

    WIDTH = 1000
    HEIGHT = 600

    main_plot = figure(
        x_axis_type="datetime",
        tools=tools,
        width=WIDTH,
        height=HEIGHT,
        title=f"{script_name}: Backtest {res.run_config_id}",
    )

    main_plot = vizz.add_bars_to_plot(main_plot, bars)
    main_plot = vizz.add_positions_to_plot(main_plot, positions)

    for t, s in zip(overlay_indicators, overlay_indicator_styles):
        main_plot = vizz.add_overlay_indicator_to_plot(main_plot, t.get_df(), s)

    sub_plots = []
    for p_conf, trackers, styles in extra_plots:
        sub_plot = figure(
            x_axis_type="datetime",
            x_range=main_plot.x_range,
            tools=tools,
            width=WIDTH,
            height=200,
            title=f"{p_conf.title}",
        )
        for t, s in zip(trackers, styles):
            sub_plot = vizz.add_overlay_indicator_to_plot(sub_plot, t.get_df(), s)
            sub_plots.append(sub_plot)

    l = column(
        main_plot,
        *sub_plots,
    )

    return l


def remove_weekends(df):
    """
    Removes weekends from a DataFrame that has a DateTime index.

    Parameters:
    df (pd.DataFrame): A DataFrame with a DateTime index.

    Returns:
    pd.DataFrame: A DataFrame with weekends removed.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DateTimeIndex.")

    # Filter out weekends (where day of the week is 5 (Saturday) or 6 (Sunday))

    return df[df.index.dayofweek < 5]


def df_from_multitracker(tracker: TrackerMulti):
    df = pd.DataFrame(
        data={
            "date": [maybe_unix_nanos_to_dt(ts) for ts in tracker.timestamps],
        }
    )
    for name, values in tracker.values.items():
        df[name] = values
    df.set_index("date", inplace=True)
    return df


def df_from_bars(bars: list[Bar]):
    # bars to pandas dataframe
    df = pd.DataFrame(
        data={
            "date": [maybe_unix_nanos_to_dt(b.ts_event) for b in bars],
            "open": [b.open.as_double() for b in bars],
            "high": [b.high.as_double() for b in bars],
            "low": [b.low.as_double() for b in bars],
            "close": [b.close.as_double() for b in bars],
            "volume": [b.volume.as_double() for b in bars],
        }
    )

    # df['date'] = pd.to_datetime(df['date'])
    df.set_index("date", inplace=True)

    # Filter out weekends
    # df = remove_weekends(df)

    # draw
    return df
