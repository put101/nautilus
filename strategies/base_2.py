import os
import threading
import datetime
from builtins import bool
from dataclasses import field
from datetime import timedelta
from typing import TypeAlias, List, Tuple
from decimal import Decimal
import pandas as pd

import enum
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed

from nautilus_trader.core.nautilus_pyo3 import (
    OrderSide,
    TimeInForce,
    OrderType,
    PositionId,
)
from nautilus_trader.model.events import (
    OrderEvent,
    OrderRejected,
    OrderCanceled,
    OrderAccepted,
    OrderFilled,
    PositionOpened,
    PositionChanged,
    PositionClosed,
)
from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.core.message import Event
from nautilus_trader.core.rust.model import PositionSide
from nautilus_trader.core.rust.model import (
    OrderSide,
    TimeInForce,
    OrderType,
    TriggerType,
)
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
from nautilus_trader.core.datetime import (
    dt_to_unix_nanos,
    maybe_unix_nanos_to_dt,
    unix_nanos_to_dt,
)

import put101.utils as utils
import put101.vizz as vizz
from put101.indicators import TrackerMulti
from put101.vizz import PlotConfig, ListStyling, LineIndicatorStyle

# time series persistence and analysis
from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError


class PUT101StrategyConfig(StrategyConfig):
    IDENTIFIER: str = None
    bucket = "nautilus"

    instrument_id: str
    bar_type: str
    emulation_trigger: str = "NO_TRIGGER"
    manage_contingent_orders = True
    # plotting, monitoring and statistics
    use_bokeh_plotting: bool = False
    write_price_data = True
    write_indicator_data = True

    IGNORE_SINGLE_PRICE_BARS: bool = True


class PUT101Strategy(Strategy):
    def __init__(self, config: PUT101StrategyConfig):
        super().__init__(config)

        # config basic parameters
        self.conf = config
        self.bar_type: BarType = BarType.from_str(config.bar_type)
        self.instrument_id: InstrumentId = InstrumentId.from_str(config.instrument_id)
        self.venue: Venue = self.instrument_id.venue
        self.emulation_trigger = TriggerType[config.emulation_trigger]

        # indicators
        self.all_indicators_ready = False
        self.indicators: list[Indicator] = []
        self.overlay_trackers: list[TrackerMulti] = []
        self.extra_trackers: list[TrackerMulti] = []

        # plotting styles
        self.overlay_styles: list[vizz.LineIndicatorStyle] = []
        self.extra_styles: list[vizz.LineIndicatorStyle] = []

        # concrete trackers
        self.portfolio_tracker: TrackerMulti = TrackerMulti(
            sub_indicator=utils.PortfolioIndicator(lambda: self.portfolio, self.venue),
            value_getters={
                "balance": lambda x: x.balance,
                "equity": lambda x: x.equity,
            },
        )
        self.indicators.append(self.portfolio_tracker)

        self.indicators.extend(self.extra_trackers)
        self.indicators.extend(self.overlay_trackers)

        self.took_position = False

        self.instrument: Instrument | None = None  # see on_start
        self.processed_bars: list[Bar] = []

        self.trade_manager = TradeManager(self)

        # Initialize the InfluxDB client
        self.client = None
        self.write_api = None
        self.callback = None

    def get_main_plottable_indicators(
        self,
    ) -> tuple[list[TrackerMulti], list[vizz.LineIndicatorStyle]]:
        return self.overlay_trackers, self.overlay_styles

    def get_extra_plots(self):
        return [
            (
                vizz.PlotConfig(title="Portfolio Tracker"),
                [self.portfolio_tracker],
                [
                    vizz.ListStyling(
                        [
                            vizz.LineIndicatorStyle("blue", 0.5, 2),
                            vizz.LineIndicatorStyle("green", 0.5, 2),
                        ]
                    )
                ],
            ),
            (
                vizz.PlotConfig(title="Extra Trackers"),
                self.extra_trackers,
                self.extra_styles,
            ),
        ]

    @property
    def bars(self) -> list[Bar]:
        return self.processed_bars

    def influx_success(self, conf: (str, str, str), data: str):
        self.log.debug(f"Written batch: {conf}, data: {data}")

    def influx_error(self, conf: (str, str, str), data: str, exception: InfluxDBError):
        self.log.error(f"Cannot write batch: {conf}, data: {data} due: {exception}")

    def influx_retry(self, conf: (str, str, str), data: str, exception: InfluxDBError):
        self.log.error(
            f"Retryable error occurs for batch: {conf}, data: {data} retry: {exception}"
        )

    def on_start(self):

        print("self.log", self.log)

        self.client = InfluxDBClient(
            url="http://localhost:8086", token=os.environ["INFLUX_TOKEN"], org="main"
        )
        self.write_api = self.client.write_api(
            write_options=WriteOptions(
                batch_size=1000,
                flush_interval=1000,
            ),
            success_callback=self.influx_success,
            error_callback=self.influx_error,
            retry_callback=self.influx_retry,
        )

        self.instrument = self.cache.instrument(self.instrument_id)

        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.instrument_id}")
            self.stop()
            return

        self.subscribe_bars(self.bar_type)

    def on_order_event(self, event: OrderEvent):
        print("OrderEvent: " + str(event))
        self.trade_manager.on_order_event(event)

    def on_event(self, event: Event):

        if isinstance(event, OrderEvent):
            self.log.info(f"OrderEvent: {event}")

        if isinstance(event, PositionEvent):
            self.log.info(f"PositionEvent: {event}")

        return

    def on_bar(self, bar: Bar) -> bool:
        """
        :param bar:
        :return: if true bar was processed, else false the bar was not processed
        """
        # debug log some objects

        if self.conf.IGNORE_SINGLE_PRICE_BARS and bar.is_single_price():
            return False

        # update indicators
        for indicator in self.indicators:
            indicator.handle_bar(bar)

        if not self.all_indicators_ready:
            for indicator in self.indicators:
                if not indicator.initialized:
                    self.log.debug(
                        "indicator not initialized, skipping this on_bar processing: "
                        + str(indicator)
                    )
                    return False
            self.all_indicators_ready = True

        self.processed_bars.append(bar)

        # influx
        if self.conf.write_price_data:
            # measure time it takes to write to influxdb

            time = datetime.datetime.now()

            price_point = (
                Point(str(bar.bar_type))
                .tag("strategy_id", self.conf.IDENTIFIER)
                .field("close", bar.close.as_double())
                .field("open", bar.open.as_double())
                .field("high", bar.high.as_double())
                .field("low", bar.low.as_double())
                .time(bar.ts_event, WritePrecision.NS)
            )

            portfolio_point = (
                Point("portfolio")
                .tag("strategy_id", self.conf.IDENTIFIER)
                .field("balance", self.portfolio_tracker.sub_indicator.balance)
                .field("equity", self.portfolio_tracker.sub_indicator.equity)
                .time(bar.ts_event, WritePrecision.NS)
            )

            self.log.debug(f"writing to influx: {price_point}, {portfolio_point}")
            try:
                self.write_api.write(
                    bucket=self.conf.bucket,
                    record=[price_point, portfolio_point],
                )
            except InfluxDBError as e:
                self.log.error(f"Error writing to influx: {e}")
                self.abort("Aborting because Error writing to influx")

            self.log.debug(f"writing to influx took: {datetime.datetime.now() - time}")

    def abort(self, msg):
        """
        abort the strategy with a reason
        :return:
        """
        print(f"ABORT: {msg}")
        self.log.error(msg)
        self.stop()

    def on_stop(self):
        self.log.info("stopping strategy")

        # stop the dash app
        self.log.info("stopping influx api_writer and client gracefully")
        self.write_api.flush()
        self.write_api.close()
        self.client.close()

        pass

    def buy(self, entry: float, sl: float, tp: float, quantity: float) -> None:
        """
        Users bracket buy method (example).
        """
        if not self.instrument:
            self.log.error("No instrument loaded.")
            return

        order_list: OrderList = self.order_factory.bracket(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(quantity),
            time_in_force=TimeInForce.GTD,
            expire_time=self.clock.utc_now() + timedelta(seconds=30),
            entry_price=self.instrument.make_price(entry),
            entry_trigger_price=self.instrument.make_price(entry),
            sl_trigger_price=self.instrument.make_price(sl),
            tp_price=self.instrument.make_price(tp),
            entry_order_type=OrderType.MARKET_IF_TOUCHED,
            emulation_trigger=self.emulation_trigger,
        )

        self.log.info("ENTRY-SUBMIT: " + str(order_list.orders))

        self.submit_order_list(order_list)

    def sell(self, entry: float, sl: float, tp: float, quantity: float) -> None:

        order_list: OrderList = self.order_factory.bracket(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(quantity),
            time_in_force=TimeInForce.GTD,
            expire_time=self.clock.utc_now() + timedelta(seconds=30),
            entry_price=self.instrument.make_price(entry),
            entry_trigger_price=self.instrument.make_price(entry),  # TODO
            sl_trigger_price=self.instrument.make_price(sl),
            tp_price=self.instrument.make_price(tp),
            entry_order_type=OrderType.MARKET_IF_TOUCHED,
            emulation_trigger=self.emulation_trigger,
        )

        self.log.info("ENTRY-SUBMIT: " + str(order_list.orders))

        self.submit_order_list(order_list)

    def close_partial_position(
        self,
        position: Position,
        partial_quantity: Quantity | Decimal | float,
        client_id=None,
        tags=None,
    ):
        """Partially close the given position.
        Parameters:
        - position (Position): The position to partially close.
        - partial_quantity (Quantity): The quantity of the position to close.
        - client_id (ClientId, optional): The specific client ID for the command. If None, then inferred from the venue in the instrument ID.
        - tags (str, optional): Tags for the market order closing the position.
        """

        if position.is_closed:
            self.log.error(
                f"Cannot partially close position (the position is already closed), {position}."
            )
            return

        if partial_quantity >= position.quantity or partial_quantity <= 0:
            self.log.error("Partial quantity is invalid.")
            return

        order_factory: OrderFactory = self.order_factory

        # ensure Quantity type
        partial_quantity = self.instrument.make_qty(partial_quantity)

        # Create a partial closing order (assuming you have a method like this)
        order = order_factory.market(
            instrument_id=position.instrument_id,
            order_side=Order.closing_side(position.side),
            quantity=partial_quantity,
            time_in_force=TimeInForce.GTC,  # Good Till Cancelled
            reduce_only=True,
            quote_quantity=False,
            exec_algorithm_id=None,  # taken from strategy.pyx: close_position
            exec_algorithm_params=None,
            tags=tags,
        )

        # Submit the order (assuming you have a method like this)
        self.submit_order(order, position_id=position.id, client_id=client_id)


class Trade(StateMachine):
    """description"""

    class TradeResult(enum.Enum):
        TP = 0
        PARTIAL_PROFIT = 1
        BE = 2
        SL = 3
        ERROR = 4

    def __init__(self):
        super().__init__()


# TODO: get rid of strategy dependency or find suited abstraction like a configuration class
class SimpleTrade(Trade):

    def __init__(self, factory, order_list: OrderList):
        super().__init__()
        self.factory = factory
        self.order_list: OrderList = order_list
        self.position_id: PositionId | None = None

    created = State("Created", initial=True)
    submitted = State("Submitted")

    entered = State("Entered")

    error = State("Error", final=True)

    finished = State("Finished", final=True)

    submit_orders = created.to(submitted)

    # TODO:

    position_found = submitted.to(entered, cond="test_position_opened")
    position_closed = entered.to(finished)
    rejection = submitted.to(error)

    def on_order_event(self, event: OrderEvent):
        first_order: Order = self.order_list.first

        if event.client_order_id == first_order.client_order_id:
            if isinstance(event, OrderRejected):
                try:
                    self.position_found()
                    self.rejection()
                except TransitionNotAllowed:
                    self.strategy.log.error(
                        f"SimpleTrade.on_order_event: OrderRejected({event.client_order_id})"
                    )

        if event.client_order_id == self.sl_order.client_order_id:
            # TODO: handle to close the trade if SL order gets rejected other scenarios
            pass

    def on_position_opened(self, event: PositionOpened):
        if event.opening_order_id == self.order_list.first.client_order_id:
            self.position_found()
            self.position_id = event.position_id
            try:
                self.error()
            except TransitionNotAllowed:
                self.strategy.log.error(
                    f"SimpleTrade.on_position_opened: PositionOpened({event.position_id})"
                )

    def get_result(self):
        pass

    def on_position_closed(self, event: PositionClosed):
        if event.position_id == self.position_id:
            self.finished()

    def submit(self):
        self.strategy.submit_order_list(self.order_list)
        self.submit()

    def pnl(self):
        pass


"""Trades are collections of Positions and corresponding Orders. 
It should abstract the process of entering different types of trades like pyramiding,scal-ins, grids, 
and mechanics like going break-even on trades or trailing the stop-loss/tp"""


class TradeFactory:
    def __init__(self, strategy: PUT101Strategy):
        self.strategy = strategy
        self.expire_seconds = 30
        self.cache: CacheFacade = strategy.cache

    def market_entry(self, entry: float, sl: float, tp: float, quantity: float):
        strategy = self.strategy

        order_side = OrderSide.BUY if entry > sl else OrderSide.SELL

        order_list: OrderList = strategy.order_factory.bracket(
            instrument_id=strategy.instrument_id,
            order_side=order_side,
            quantity=strategy.instrument.make_qty(quantity),
            time_in_force=TimeInForce.GTD,
            expire_time=strategy.clock.utc_now()
            + timedelta(seconds=self.expire_seconds),
            entry_price=strategy.instrument.make_price(entry),
            entry_trigger_price=strategy.instrument.make_price(entry),
            sl_trigger_price=strategy.instrument.make_price(sl),
            tp_price=strategy.instrument.make_price(tp),
            entry_order_type=OrderType.MARKET_IF_TOUCHED,
            emulation_trigger=strategy.emulation_trigger,
        )

        trade = SimpleTrade(self, order_list)
        return trade


class TradeManager:
    def __init__(self, strategy):
        self.strategy: PUT101Strategy = strategy
        self.cache = strategy.cache
        self.trade_factory = TradeFactory(strategy)
        self.trades = []

    def manage_trade(self, trade):
        self.trades.append(trade)

    def on_order_event(self, order_event):
        # pass on the event to the trades and let them update their state
        for trade in self.trades:
            trade.on_order_event(order_event)
        pass


class DrawdownMonitor:
    class Config:
        def __init__(self, max_drawdown: float):
            self.max_drawdown = max_drawdown

    def __init__(self, strategy, config: Config):
        self.strategy = strategy
        self.config = config
        self.high_mark = strategy.account.balance(
            strategy.account.currencies()[0]
        ).total.as_double()
        self.max_drawdown = config.max_drawdown
        self.max_drawdown_reached = False

        self.portfolio: Portfolio = strategy.portfolio
        self.account: Account = self.portfolio.account(strategy.venue)
        # cache: CacheFacade = self.cache
        # balance_free: float = balance.free.as_double()
        # balance_locked: float = balance.locked.as_double()

    def update(self):
        """
        update the draw_down and max_draw_down
        :return:
        """
        balance: AccountBalance = self.account.balance(self.account.currencies()[0])
        balance_total: float = balance.total.as_double()
        self.drawdowns.append(balance_total)

        if balance_total > self.high_mark:
            self.high_mark = balance_total

        if balance_total < self.high_mark * self.max_drawdown:
            self.max_drawdown_reached = True

    def drawdown_ok(self):
        return not self.max_drawdown_reached
