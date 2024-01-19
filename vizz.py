# This file defines stuff used all over the place for my plotting of my strategies.
from nautilus_trader.backtest.engine import BacktestResult
from nautilus_trader.core.datetime import maybe_unix_nanos_to_dt
from nautilus_trader.model.position import Position
from nautilus_trader.model.data import Bar,BarType,BarSpecification
from bokeh.plotting import figure, curdoc, output_notebook, reset_output
from bokeh.io import output_notebook, push_notebook, show
from bokeh.models import ColumnDataSource, DatetimePicker, Button, TextInput, DatetimeTickFormatter
from bokeh.layouts import column, row
from bokeh.models import HoverTool
import bokeh.colors.color
import pandas as pd
import datetime

# ------- MY CODE -------
import utils
import indicators
from indicators import TrackerMulti




# create line withs enum
from enum import Enum

class LineWidth:
    THIN = 1
    MEDIUM = 4
    THICK = 9


def add_overlay_indicator_scatter_to_plot(p: figure, indicator: TrackerMulti, color: str = "black", **kwargs) -> figure:
    df = indicator.get_df()

    for i, col in enumerate(df.columns):
        p.scatter(df.index, df[col], color=color, **kwargs)

    return p


def add_overlay_indicator_to_plot(p: figure, tracker: TrackerMulti,
                                  colors: list[str] | None = None,
                                  alphas: list[str] | None = None,
                                  line_widths: list[int] | None = None,
                                  **kwargs) -> figure:
    print("adding overlay indicator", tracker.sub_indicator.name)

    df = tracker.get_df()
    df = utils.remove_weekends(df)

    if colors is None:
        colors = ["black"] * len(df.columns)

    if alphas is None:
        alphas = [0.2] * len(df.columns)

    if line_widths is None:
        line_widths = [LineWidth.THIN] * len(df.columns)

    for i, col in enumerate(df.columns):
        print("adding line", col)
        p.line(df.index, df[col], color=colors[i], alpha=alphas[i], line_width=line_widths[i], **kwargs)
    return p


def add_positions_to_plot(p, positions: list[Position]):
    df = pd.DataFrame([p.to_dict() for p in positions])

    # only use relevant columns to avoid warnings about "too large int values" from bokeh
    df = df[["ts_opened", "avg_px_open", "ts_closed", "avg_px_close", "realized_pnl", "realized_return", "peak_qty"]]
    winners = df["realized_return"].astype(float) > 0
    loosers = df["realized_return"].astype(float) <= 0

    df["ts_opened"] = df["ts_opened"].apply(lambda x: maybe_unix_nanos_to_dt(x))
    df["ts_closed"] = df["ts_closed"].apply(lambda x: maybe_unix_nanos_to_dt(x))

    renderers = [
        # winners
        p.segment("ts_opened", "avg_px_open", "ts_closed", "avg_px_close", source=df[winners], color="green",
                  line_width=2, line_alpha=0.5, line_dash="dotted"),
        # loosers
        p.segment("ts_opened", "avg_px_open", "ts_closed", "avg_px_close", source=df[loosers], color="tomato",
                  line_width=2, line_alpha=0.5, line_dash="dotted"),
    ]

    p.circle("ts_opened", "avg_px_open", source=df, color="green", size=4),
    p.circle("ts_closed", "avg_px_close", source=df, color="tomato", size=4),

    # add pnl hover tooltip
    p.add_tools(HoverTool(tooltips=[("peak_qty", "@peak_qty"),
                                    ("realized_pnl", "@realized_pnl"),
                                    ("realized_return", "@realized_return"),
                                    ], renderers=renderers, mode="vline"))

    return p


def add_bars_to_plot(p, bars: list[Bar]):
    # empty bars
    if len(bars) == 0:
        return p

    bar_df = utils.df_from_bars(bars)

    # print(bar_df.index)
    # print(bar_df.columns)
    # print(bar_df.head())

    # return p

    # p.xaxis.major_label_overrides = {
    #    i: date.strftime('%b %d') for i, date in enumerate(pd.to_datetime(bar_df.index))
    # }

    # p.xaxis.major_label_overrides = {
    #   i: ts.strftime('%Y-%m-%d %H:%S') for i, ts in enumerate(bar_df.index)
    # }

    # bar_df = utils.remove_weekends(bar_df)

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


def get_layout(res: BacktestResult, bars: list[Bar], line_indicators: list[TrackerMulti], positions: list[Position], sync_axis=None,
               picker_start=None, picker_end=None):
    # add all wheel zoom
    tools = "pan,xwheel_zoom,ywheel_zoom,wheel_zoom,box_zoom,reset,save"

    p = figure(x_axis_type="datetime", tools=tools, width=1000, height=600, title=f"Backtest {res.run_config_id}")

    p = add_bars_to_plot(p, bars)
    p = add_positions_to_plot(p, positions)
    # add additional markers for positions

    for t in line_indicators:
        p = add_overlay_indicator_to_plot(p, t)

    text1 = TextInput(title="title", value='value')
    picker_start = DatetimePicker(title="Start", value=picker_start)
    picker_end = DatetimePicker(title="End", value=picker_end, max_date=datetime.now())
    button = Button(label="button", button_type="success")
    button.on_click(lambda: print("button clicked"))

    layout = column(
        row(text1, button),
        row(picker_start, picker_end),
        p
    )

    return layout

