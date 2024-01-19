# nautilus
from enum import Enum

import pandas as pd
from nautilus_trader.config.backtest import BacktestRunConfig, BacktestEngineConfig, BacktestVenueConfig
from nautilus_trader.core.datetime import maybe_unix_nanos_to_dt
from nautilus_trader.core.rust.model import PositionSide, OrderSide, TimeInForce, OrderType
from nautilus_trader.model.data import Bar
from nautilus_trader.model.orders import OrderList
from nautilus_trader.model.position import Position

# others
import mplfinance as mpf
from datetime import timedelta
import matplotlib.pyplot as plt
from matplotlib.pyplot import figure, axes
from matplotlib.figure import Figure
from matplotlib.axes import Axes


import plotly.graph_objects as go
from pandas import Timestamp

# mine
from indicators import TrackerFloat, TrackerMulti


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


def get_empty_figure_matplotlib() -> (Figure, Axes):
    fig, ax = plt.subplots()
    return fig, ax



def df_from_multitracker(tracker: TrackerMulti):
    df = pd.DataFrame(data={
        'date': [maybe_unix_nanos_to_dt(ts) for ts in tracker.timestamps],
    })
    for name, values in tracker.values.items():
        df[name] = values
    df.set_index('date', inplace=True)
    return df


def df_from_bars(bars: list[Bar]):
    # bars to pandas dataframe
    df = pd.DataFrame(data={
        'date': [maybe_unix_nanos_to_dt(b.ts_event) for b in bars],
        'open': [b.open.as_double() for b in bars],
        'high': [b.high.as_double() for b in bars],
        'low': [b.low.as_double() for b in bars],
        'close': [b.close.as_double() for b in bars],
        'volume': [b.volume.as_double() for b in bars],
    })

    #df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    # Filter out weekends
    #df = remove_weekends(df)

    # draw
    return df

def get_empty_figure(bg_color=None, paper_bg_color=None) -> go.Figure:
    fig = go.Figure(data=[go.Candlestick(x=[], open=[], high=[], low=[], close=[])], layout=go.Layout(
        plot_bgcolor=bg_color,
        paper_bgcolor=paper_bg_color,
    ))
    fig.update_layout(title='Live Trading Chart', xaxis_title='Date', yaxis_title='Price')
    # without slider
    fig.update_layout(xaxis_rangeslider_visible=False)

    # hide weekends
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    return fig


def draw_rectangle(fig: go.Figure, x0: Timestamp, y0: float, x1: Timestamp, y1: float, color: str):
    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        fillcolor=color,
        opacity=0.2,
        line_width=0,
    )
    return fig


def draw_positions(fig: go.Figure, positions: list[Position]):
    for pos in positions:
        side: OrderSide = pos.entry
        color = "green" if side == OrderSide.BUY else "red" if side == OrderSide.SELL else "black"

        fig.add_trace(go.Scatter(
            x=[maybe_unix_nanos_to_dt(pos.ts_opened), maybe_unix_nanos_to_dt(pos.ts_closed)],
            y=[pos.avg_px_open, pos.avg_px_close],
            mode="lines",
            line=dict(color=color, width=2),
            name=f"{pos.id}",
            showlegend=False
        ))
    return fig


def trace_from_multitracker(tracker: TrackerMulti, name: str, color: str):
    traces = []
    for name, values in tracker.values.items():
        traces.append(go.Scatter(
            x=[maybe_unix_nanos_to_dt(ts) for ts in tracker.timestamps],
            y=values,
            mode="lines",
            line=dict(color=color, width=2),
            name=name
        ))
    return traces


def trace_from_bars(bars: list[Bar]):
    return go.Candlestick(
        x=[maybe_unix_nanos_to_dt(b.ts_event) for b in bars],
        open=[b.open.as_double() for b in bars],
        high=[b.high.as_double() for b in bars],
        low=[b.low.as_double() for b in bars],
        close=[b.close.as_double() for b in bars],
    )


def add_bars(fig: go.Figure, bars: list[Bar]):
    # filter out timestamps with no data / e.g weekends
    fig.add_trace(go.Candlestick(
        x=[maybe_unix_nanos_to_dt(b.ts_event) for b in bars],
        open=[b.open.as_double() for b in bars],
        high=[b.high.as_double() for b in bars],
        low=[b.low.as_double() for b in bars],
        close=[b.close.as_double() for b in bars],
    ))

    fig.update_layout()
    return fig


def add_markers(fig: go.Figure, x_ts: list[Timestamp], ys: list[float], name: str = "marker", color: str = "lime",
                size: int = 4):
    fig.add_trace(go.Scatter(
        x=x_ts,
        y=ys,
        mode="markers",
        marker=dict(color=color, size=size),
        name=name
    ))
    return fig


def add_multiline_indicator(fig: go.Figure, tracker: TrackerMulti, color: str):
    for name, values in tracker.values.items():
        fig.add_trace(go.Scatter(
            x=[maybe_unix_nanos_to_dt(ts) for ts in tracker.timestamps],
            y=values,
            mode="lines",
            line=dict(color=color, width=2),
            name=name
        ))
    return fig
