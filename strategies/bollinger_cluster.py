import datetime
import threading
from builtins import bool
from dataclasses import field
from datetime import timedelta
from typing import TypeAlias
from decimal import Decimal
import pandas as pd

from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.core.message import Event
from nautilus_trader.core.rust.model import PositionSide
from nautilus_trader.core.rust.model import OrderSide, TimeInForce, OrderType, TriggerType
from nautilus_trader.indicators.base.indicator import Indicator
from nautilus_trader.indicators.bollinger_bands import BollingerBands
from nautilus_trader.indicators.average.moving_average import MovingAverage
from nautilus_trader.indicators.rsi import RelativeStrengthIndex
from nautilus_trader.model.data import BarType, Bar, QuoteTick
from nautilus_trader.model.events import OrderEvent, PositionEvent
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.identifiers import Venue, InstrumentId, PositionId
from nautilus_trader.model.objects import Quantity, Currency, Money, AccountBalance
from nautilus_trader.model.orders import OrderList, Order
from nautilus_trader.model.position import Position
from nautilus_trader.portfolio import Portfolio
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.strategy import StrategyConfig
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.core.datetime import dt_to_unix_nanos, maybe_unix_nanos_to_dt, unix_nanos_to_dt

from put101 import utils
import put101.vizz as vizz
from put101.indicators import TrackerMulti

import put101
import strategies.base as base

percent: TypeAlias = float


class BollingerClusterConfig(StrategyConfig):
    base_config: base.PUT101StrategyConfig

    bb_params: list[tuple[
        int,  # period
        float  # std
    ]]

    USE_TRADING_HOURS: bool = True
    TRADING_SESSIONS: list[tuple[int, int]] = field(
        default_factory=lambda: [(0, 24)])
    PARTIAL_RATIO: float | None = None


class BollingerCluster(base.PUT101Strategy):
    def __init__(self, config: BollingerClusterConfig):
        super().__init__(config.base_config)
        self.conf = config
        # draw-down monitor stuff
        self.max_dd = 0.10
        self.max_profit = 0.10

        # bollinger band stuff
        self.bands: list[BollingerBands] = [BollingerBands(
            period, std) for period, std in self.conf.bb_params]

        bollinger_getters = {
            "lower": lambda x: x.lower,
            "middle": lambda x: x.middle,
            "upper": lambda x: x.upper
        }

        for b in self.bands:
            self.overlay_trackers.append(TrackerMulti(
                b, value_getters=bollinger_getters))
            self.overlay_styles.append(vizz.LineIndicatorStyle("blue", 0.5, 2))

        from nautilus_trader.indicators.average.ma_factory import MovingAverageFactory, MovingAverageType
        ma_getters = {
            "ma": lambda x: x.value
        }

        self.ema_slow = MovingAverageFactory.create(
            50, MovingAverageType.EXPONENTIAL)
        self.overlay_trackers.append(TrackerMulti(
            self.ema_slow, value_getters=ma_getters))
        self.overlay_styles.append(vizz.LineIndicatorStyle("black", 0.5, 2))

        self.ema_fast = MovingAverageFactory.create(
            30, MovingAverageType.EXPONENTIAL)
        self.overlay_trackers.append(TrackerMulti(
            self.ema_fast, value_getters=ma_getters))
        self.overlay_styles.append(vizz.LineIndicatorStyle("red", 0.5, 2))

        self.atr = AverageTrueRange(7)
        self.atr_tracker = TrackerMulti(self.atr, value_getters={
            "atr": lambda x: x.value})
        self.indicators.append(self.atr_tracker)

        for i in [
            RelativeStrengthIndex(14)]:
            self.extra_trackers.append(TrackerMulti(
                i, value_getters={"value": lambda x: x.value}))
            self.extra_styles.append(vizz.LineIndicatorStyle("red", 0.5, 2))
        self.indicators.extend(self.extra_trackers)

        self.indicators.extend(self.overlay_trackers)

        self.balances_timestamps = []
        self.balances = []

    def get_main_plottable_indicators(self) -> tuple[list[TrackerMulti], list[vizz.LineIndicatorStyle]]:
        return self.overlay_trackers, self.overlay_styles

    def get_extra_plots(self):
        return [(vizz.PlotConfig(title="Portfolio Tracker"), [self.portfolio_tracker], [
            vizz.ListStyling([vizz.LineIndicatorStyle("blue", 0.5, 2), vizz.LineIndicatorStyle("green", 0.5, 2)])]),
                (vizz.PlotConfig(title="Extra Trackers"), self.extra_trackers, self.extra_styles),
                ]

    @property
    def bars(self) -> list[Bar]:
        return self.processed_bars

    def on_start(self):
        super().on_start()
        return

    def on_event(self, event: Event):

        if isinstance(event, OrderEvent):
            self.log.info(f"OrderEvent: {event}")

        if isinstance(event, PositionEvent):
            self.log.info(f"PositionEvent: {event}")

        return

    def on_bar(self, bar: Bar):
        # respect base strategy implementation
        if not super().on_bar(bar):
            return

        portfolio: Portfolio = self.portfolio
        account: Account = portfolio.account(self.venue)
        balance: AccountBalance = account.balance(account.currencies()[0])
        cache: CacheFacade = self.cache
        balance_total: float = balance.total.as_double()
        balance_free: float = balance.free.as_double()
        balance_locked: float = balance.locked.as_double()
        order_factory: OrderFactory = self.order_factory
        is_flat: bool = portfolio.is_flat(self.instrument_id)

        if balance.total.as_double() < 10_000 * 0.90:
            self.log.error("balance too low, stopping strategy")
            self.stop()

        if not is_flat:
            pnl = portfolio.unrealized_pnl(self.instrument_id)
            cur_max_dd = balance.total.as_double() * self.max_dd
            min_pnl = -abs(cur_max_dd)
            if pnl and pnl.as_double() < min_pnl:
                self.log.error(
                    f"Max DD reached: {pnl.as_double()} < {min_pnl}, closing all positions")
                self.close_all_positions(self.instrument_id)

            cur_max_profit = balance.total.as_double() * self.max_profit
            max_pnl = abs(cur_max_profit)
            if pnl and pnl.as_double() > max_pnl:
                if not self.conf.PARTIAL_RATIO:
                    self.log.warn(
                        f"cannot close partials, no PARTIAL_RATIO set")
                self.log.error(
                    f"Max PNL reached: {pnl.as_double()} > {max_pnl}, closing partial positions")
                # self.close_all_positions(self.instrument_id)
                positions_open: list[Position] = self.cache.positions_open(
                    venue=None,  # Faster query filtering
                    instrument_id=self.instrument_id,
                    side=PositionSide.NO_POSITION_SIDE
                )
                for pos in positions_open:
                    if self.conf.PARTIAL_RATIO is not None:
                        partial_quantity = pos.quantity * self.conf.PARTIAL_RATIO
                        self.close_partial_position(pos,
                                                    partial_quantity,
                                                    tags=f"PARTIAL-maxpnl : {str(self.conf.PARTIAL_RATIO)}")
                    else:
                        self.abort("PARTIAL_RATIO not set check config")

        POINT_SIZE = float(self.instrument.price_increment)
        PIP_SIZE = 10 * POINT_SIZE

        MIN_SL_POINTS = 20
        ATR_SL_FACTOR = 1
        TP_FACTOR = 10

        SL_POINTS = ATR_SL_FACTOR * (self.atr.value / POINT_SIZE)
        SL_POINTS = max(SL_POINTS, MIN_SL_POINTS)

        TP_POINTS = SL_POINTS * TP_FACTOR

        RISK_PER_TRADE = self.max_dd / 2

        RISK = RISK_PER_TRADE * balance_total

        # self.log.info("last tick: " + str(cache.quote_ticks(self.instrument_id)[-1]))

        qty = utils.RiskCalculator.qty_from_risk(entry=bar.close.as_double(),
                                                 exit=bar.close.as_double() + SL_POINTS * float(
                                                     self.instrument.price_increment),
                                                 risk=RISK,
                                                 ins=self.instrument)

        buy_signal = False
        sell_signal = False

        # SIGNAL COMPOSITION

        ts = maybe_unix_nanos_to_dt(bar.ts_event)

        # trading hours rules
        USE_TRADING_HOURS: bool = bool(self.conf.USE_TRADING_HOURS)
        TRADING_HOURS_START = 8
        TRADING_HOURS_END = 17

        if USE_TRADING_HOURS and not utils.in_session_hours(self.conf.TRADING_SESSIONS, ts):
            return

        up_trend = self.ema_fast.value > self.ema_slow.value
        down_trend = self.ema_fast.value < self.ema_slow.value

        if up_trend and self.bands[0].lower > bar.close.as_double():
            buy_signal = True
        if down_trend and self.bands[0].upper < bar.close.as_double():
            sell_signal = True

        WINDOW = 20
        N = WINDOW
        if len(self.bars) < WINDOW:
            self.log.error("not enough bars for dataframe window size")
            return

        df = utils.df_from_bars(self.bars)[-WINDOW:]

        df = pd.merge(df, self.atr_tracker.get_df(), left_index=True, right_index=True, how='left')

        df["bullish"] = (df['close'] > df['open']).astype(int)
        df['bullish_count'] = df['bullish'].rolling(window=N).sum()

        def count_false(values):
            return len([v for v in values if not v])

        df['bearish_count'] = df['bullish'].rolling(window=N).apply(lambda w: count_false(w), raw=True)

        # df['spikes_above'] = self.bb.

        # SIGNAL EXECUTION

        if is_flat:
            if buy_signal:
                self.buy(bar.close.as_double(), bar.close.as_double(
                ) - SL_POINTS * POINT_SIZE, bar.close.as_double() + TP_POINTS * POINT_SIZE, qty)

            if sell_signal:
                self.sell(bar.close.as_double(), bar.close.as_double(
                ) + SL_POINTS * POINT_SIZE, bar.close.as_double() - TP_POINTS * POINT_SIZE, qty)


        # implement logic that saves everything to a timeseries database for later analysis / live analysis
        # in grafana



        pass

    def on_stop(self):
        super().on_stop()
        pass
