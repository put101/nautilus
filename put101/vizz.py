# This file defines stuff used all over the place for my plotting of my strategies.
from nautilus_trader.core.datetime import maybe_unix_nanos_to_dt
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.position import Position
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from bokeh.plotting import figure, curdoc, output_notebook, reset_output
from bokeh.io import output_notebook, push_notebook, show
from bokeh.models import ColumnDataSource, DatetimePicker, Button, TextInput, DatetimeTickFormatter
from bokeh.layouts import column, row
from bokeh.models import HoverTool
import bokeh.colors.color
import pandas as pd
from datetime import datetime
from typing import Optional

# ------- MY CODE -------
import put101.utils as utils
import put101.indicators as indicators

# create line withs enum
from enum import Enum


class LineWidth:
    THIN = 1
    MEDIUM = 4
    THICK = 9


class Styling:
    def to_dict(self):
        pass


class PlotConfig:
    def __init__(self, title: str):
        self.title = title

    def to_dict(self):
        return {
            "title": self.title
        }


class LineIndicatorStyle(Styling):
    def __init__(self, color: str, alpha: float, line_width: int):
        self.color = color
        self.alpha = alpha
        self.line_width = line_width

    def __repr__(self):
        return f"LineIndicatorStyle({self.color}, {self.alpha}, {self.line_width})"

    def to_dict(self):
        return {
            "color": self.color,
            "alpha": self.alpha,
            "line_width": self.line_width
        }


def add_overlay_indicator_scatter_to_plot(p: figure, df: pd.DataFrame,
                                          styling: Styling) -> figure:
    for i, col in enumerate(df.columns):
        p.scatter(df.index, df[col], **styling.to_dict())

    return p


def add_overlay_indicator_to_plot(p: figure,
                                  df: pd.DataFrame,
                                  styling: Styling,
                                  **kwargs) -> figure:
    print("adding overlay indicator", df.info)

    for i, col in enumerate(df.columns):
        print("adding line", col)
        p.line(x=df.index, y=df[col], **styling.to_dict())
    return p


def add_position_orderfills_to_plot(p: figure, fills: list[OrderFilled]):
    df = pd.DataFrame([o.to_dict() for o in fills])

    df["ts_event"] = df["ts_event"].apply(lambda x: maybe_unix_nanos_to_dt(x))

    # only use relevant columns to avoid warnings about "too large int values" from bokeh
    df = df[["ts_event", "last_px", "last_qty", "side", "order_id"]]

    # add orderfills
    p.circle("ts_event", "last__px", source=df, color="black", size=10),

    # add hover tooltip
    p.add_tools(HoverTool(tooltips=[("last_qty", "@last_qty"),
                                    ("side", "@side"),
                                    ("position_id", "@position_id"),
                                    ("order_id", "@order_id")
                                    ]))

    return p

def add_positions_to_plot(p, positions: list[Position]):
    if not positions or len(positions) == 0:
        print("No positions to plot.")
        return p

    df = pd.DataFrame([p.to_dict() for p in positions])

    df["ts_opened"] = df["ts_opened"].apply(lambda x: maybe_unix_nanos_to_dt(x))
    df["ts_closed"] = df["ts_closed"].apply(lambda x: maybe_unix_nanos_to_dt(x))
    

    # only use relevant columns to avoid warnings about "too large int values" from bokeh
    df = df[["ts_opened", "avg_px_open", "ts_closed", "avg_px_close", "realized_pnl", "realized_return", "peak_qty",
             "side", "position_id", "opening_order_id"]]

    df_all = df

    # closed positions
    winners = df["realized_return"].astype(float) > 0
    loosers = df["realized_return"].astype(float) < 0
    # others (e.g all that are still open)
    others = ~(winners | loosers) # or realized_return == 0 

    running = df["side"] != "FLAT"
    closed = ~running

    # filter out others
    df = df[~others]

    renderers = [
        # winners
        p.segment("ts_opened", "avg_px_open", "ts_closed", "avg_px_close", source=df[winners], color="green",
                  line_width=3, line_alpha=1, line_dash="dotted"),
        # loosers
        p.segment("ts_opened", "avg_px_open", "ts_closed", "avg_px_close", source=df[loosers], color="tomato",
                  line_width=3, line_alpha=1, line_dash="dotted"),
    ]

    p.circle("ts_opened", "avg_px_open", source=df[closed], color="green", size=10),
    p.circle("ts_closed", "avg_px_close", source=df[closed], color="tomato", size=10),


    # open positions (mostly for debugging as only the last ones should be open)
    p.circle("ts_opened", "avg_px_open", source=df_all[running], color="pink", size=20),


    # add pnl hover tooltip
    p.add_tools(HoverTool(tooltips=[("peak_qty", "@peak_qty"),
                                    ("realized_pnl", "@realized_pnl"),
                                    ("realized_return", "@realized_return"),
                                    ("side", "@side"),
                                    ("position_id", "@position_id"),
                                    ("opening_order_id", "@opening_order_id")
                                    ], renderers=renderers, mode="vline"))

    return p


def add_bars_to_plot(p, bars: list[Bar]):
    # empty bars
    if len(bars) == 0:
        return p

    bar_df = utils.df_from_bars(bars)

    # ohlc bars
    inc = bar_df.close > bar_df.open
    dec = bar_df.open > bar_df.close

    bar_type: BarType = bars[0].bar_type
    bar_spec: BarSpecification = bar_type.spec

    width_ms = int(bar_spec.timedelta.total_seconds() * 1000 / 2)
    p.segment(bar_df.index, bar_df.high, bar_df.index, bar_df.low, color="black")
    p.vbar(bar_df.index[inc], width=width_ms, top=bar_df.open[inc], bottom=bar_df.close[inc], fill_color="blue",
           line_color="black")
    p.vbar(bar_df.index[dec], width=width_ms, top=bar_df.open[dec], bottom=bar_df.close[dec], fill_color="black",
           line_color="black")

    return p

