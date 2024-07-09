import logging

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

from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
import enum


class TradeResult(enum.Enum):
    TP = 0
    PARTIAL_PROFIT = 1
    BE = 2
    SL = 3
    ERROR = 4

class SimpleTrade(StateMachine):

    def __init__(self, strategy: Strategy, write_points, order_list: OrderList):
        self.log = strategy.log
        self.write_points = write_points
        self.strategy: Strategy = strategy
        self.order_id = order_list.id
        self.order_list: OrderList = order_list
        self.entry_order: Order = order_list.orders[0]
        self.sl_order: Order = order_list.orders[1]
        self.tp_order: Order = order_list.orders[2]
        self.position_id: PositionId = None
        super().__init__() # respect super, but we need stuff before the transitions are called

    state_created = State("Created", value=0, initial=True)
    state_submitted = State("Submitted", value=1)
    state_accepted = State("Accepted", value=2)
    state_entered = State("Entered", value=3)
    state_error = State("Error", value=4, final=True)
    state_finished = State("Finished", value=5, final=True)

    submit_orders = state_created.to(state_submitted)
    order_list_accepted = state_submitted.to(state_accepted)

    position_found = state_accepted.to(state_entered) | state_submitted.to(state_entered)

    position_got_closed = state_entered.to(state_finished)

    entry_rejection = state_submitted.to(state_error)
    sl_rejection = state_entered.to(state_error)
    tp_rejection = state_entered.to(state_error)


    def __str__(self):
        return f"SimpleTrade({self.order_id})"

    def summary(self):
        self.log.debug(f"SimpleTrade.summary: {self}")
        return str({
            "id": self.order_id,
            "state_id": self.current_state.id,
            "state_value": self.current_state_value,
            "position_id": str(self.position_id),
        })

    def make_point(self, time, event: None):
        self.log.debug(f"SimpleTrade.make_point: {time}, {event}")
        point = Point("trade")
        point.tag("strategy_id", self.strategy.conf.IDENTIFIER)
        point.tag("id", self.order_id)
        point.field("state_id", self.current_state.id)
        point.field("state_value", self.current_state.value)
        point.field("entry_order_id", self.entry_order.client_order_id.value)
        point.field("sl_order_id", self.sl_order.client_order_id.value)
        point.field("tp_order_id", self.tp_order.client_order_id.value)
        point.field("position_id", str(self.position_id))
        point.field("event", str(event))
        point.time(time, WritePrecision.NS)
        return point

    def on_exit_state(self, event, state):

        self.log.info(f"Exiting '{state.id}' state from '{event}' event.")
        self.log.info(self.summary())

    def on_enter_state(self, event, state):
        self.log.info(f"Entering '{state.id}' state from '{event}' event.")
        self.log.info(self.summary())
        self.write_points([self.make_point(self.strategy.clock.utc_now(), event)])



    def on_order_event(self, event: OrderEvent):
        self.log.debug(f"SimpleTrade.on_order_event: {event}")
        if isinstance(event, OrderAccepted):
            self.on_order_accepted(event)
        elif isinstance(event, OrderFilled):
            self.on_order_filled(event)
        elif isinstance(event, OrderRejected):
            self.on_order_rejected(event)
        else:
            self.log.error(f"SimpleTrade.on_order_event: unknown event ")

    def on_position_event(self, event: PositionEvent):
        self.log.debug(f"SimpleTrade.on_position_event: {event}")
        if isinstance(event, PositionOpened):
            self.on_position_opened(event)
        elif isinstance(event, PositionClosed):
            self.on_position_closed(event)
        else:
            self.log.error(f"SimpleTrade.on_position_event: unknown event {str(event)}")

    def on_order_accepted(self, event: OrderAccepted):
        self.log.debug(f"SimpleTrade.on_order_accepted: {event}")
        if event.client_order_id == self.entry_order.client_order_id:
            try:
                self.order_list_accepted()
            except TransitionNotAllowed:
                self.log.error(
                    f"SimpleTrade.on_order_event: OrderAccepted({event.client_order_id})"
                )

    def on_order_filled(self, event: OrderFilled):
        self.log.debug(f"SimpleTrade.on_order_filled: {event}")
        # TODO: add TP, SL, partial fills, etc.
        pass

    def on_order_rejected(self, event: OrderRejected):
        self.log.debug(f"SimpleTrade.on_order_rejected: {event}")
        try:
            if event.client_order_id == self.entry_order.client_order_id:
                self.log.error("XXX OrderRejected SimpleTrade on_order_event")
                self.entry_rejection()

            if event.client_order_id == self.tp_order.client_order_id:
                self.log.error("XXX OrderRejected SimpleTrade on_order_event")
                self.tp_rejection()

            if event.client_order_id == self.sl_order.client_order_id:
                self.log.error("XXX OrderRejected SimpleTrade on_order_event")
                self.sl_rejection()

        except TransitionNotAllowed as e:
            self.log.error(
                f"SimpleTrade.on_order_event: OrderRejected({event.client_order_id}), {e}"
            )

    def on_position_opened(self, event: PositionOpened):
        if event.opening_order_id == self.order_list.first.client_order_id:
            self.position_id = event.position_id
            self.log.info(f"Found position {self.position_id}")
            try:
                self.position_found()
            except TransitionNotAllowed as e:
                self.log.error(
                    f"SimpleTrade.on_position_opened: PositionOpened({event.position_id})"
                )

    def on_position_closed(self, event: PositionClosed):
        self.log.debug(f"SimpleTrade.on_position_closed: self {self}")
        if self.position_id is not None:
            if self.position_id.value == event.position_id.value:
                self.log.info(f"SimpleTrade.on_position_closed: matching position found {event}")
                try:
                    self.position_got_closed()
                except Exception as e:
                    self.log.error(
                        f"SimpleTrade.on_position_closed: PositionClosed({event.position_id})"
                    )

    def submit(self):
        self.strategy.submit_order_list(self.order_list)
        self.submit_orders()

    def close(self):
        if self.current_state == self.state_entered:
            #self.strategy.close_position(self.position_id) # TODO position vs. position_id
            self.position_closed()
        else:
            self.log.info("SimpleTrade.close: not in entered state, nothing to do but SUS")
