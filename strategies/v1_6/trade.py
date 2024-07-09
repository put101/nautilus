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

from influxdb_client import Point

from strategies.v1_6.base import PUT101StrategyConfig, PUT101Strategy


class SimpleTrade(StateMachine):

    def __init__(self, strategy: PUT101Strategy, order_list: OrderList):
        super().__init__()
        self.log = strategy.log
        self.strategy: PUT101Strategy = strategy
        self.id = order_list.id
        self.order_list: OrderList = order_list
        self.entry_order: Order = order_list.orders[0]
        self.sl_order: Order = order_list.orders[1]
        self.tp_order: Order = order_list.orders[2]

        self.position_id: PositionId | None = None

    created = State("Created", initial=True)
    submitted = State("Submitted")
    accepted = State("Accepted")
    entered = State("Entered")
    error = State("Error")
    finished = State("Finished", final=True)

    submit_orders = created.to(submitted)
    orderlist_accepted = submitted.to(accepted)
    position_found = accepted.to(entered)
    position_closed = entered.to(finished)
    rejection = submitted.to(error)


    def on_position_event(self, event: PositionEvent):
        if isinstance(event, PositionOpened):
            self.on_position_opened(event)
        if isinstance(event, PositionClosed):
            self.on_position_closed(event)
        if isinstance(event, PositionChanged):
            pass

    def on_order_event(self, event: OrderEvent):

        if event.client_order_id == self.entry_order.client_order_id:
            if isinstance(event, OrderFilled):
                pass

            if isinstance(event, OrderAccepted):
                self.log.debug(f"SimpleTrade.on_order_event: OrderAccepted({event.client_order_id})")
                try:
                    self.orderlist_accepted()
                except TransitionNotAllowed:
                    self.log.error(
                        f"SimpleTrade.on_order_event: OrderAccepted({event.client_order_id})"
                    )
            if isinstance(event, OrderRejected):
                try:
                    if self.current_state == self.entered:
                        if event.client_order_id == self.tp_order.client_order_id:
                            self.log.error("XXX OrderRejected SimpleTrade on_order_event")
                            self.rejection()

                        if event.client_order_id == self.sl_order.client_order_id:
                            self.log.error("XXX OrderRejected SimpleTrade on_order_event")
                            self.rejection()

                except TransitionNotAllowed:
                    self.log.error(
                        f"SimpleTrade.on_order_event: OrderRejected({event.client_order_id})"
                    )

    def on_position_opened(self, event: PositionOpened):
        if event.opening_order_id == self.order_list.first.client_order_id:
            self.position_id = event.position_id
            try:
                self.position_found()
            except TransitionNotAllowed as e:
                self.log.error(
                    f"SimpleTrade.on_position_opened: TransitionNotAllowed PositionOpened({event.position_id}), {e}"
                )

    def on_position_closed(self, event: PositionClosed):
        if event.position_id == self.position_id:
            self.position_closed()

    def submit(self):
        self.factory.strategy.submit_order_list(self.order_list)
        self.submit_orders()

    def close(self):
        if self.current_state == self.entered:
            self.strategy.close_position(self.position_id)
            self.position_closed()
        else:
            self.log.info("SimpleTrade.close: not in entered state, nothing to do but SUS")


"""Trades are collections of Positions and corresponding Orders. 
It should abstract the process of entering different types of trades like pyramiding,scal-ins, grids, 
and mechanics like going break-even on trades or trailing the stop-loss/tp"""


class TradeManager:
    def __init__(self, strategy):
        self.strategy: PUT101Strategy = strategy
        self.log = self.strategy.log
        self.cache: CacheFacade = strategy.cache
        self.trade_factory = TradeFactory(strategy)
        self.trades: list[SimpleTrade] = []
        self.finished_trades: list[SimpleTrade] = []

    def number_active_trades(self):
        return len(self.trades)

    def buy(self, entry: float, sl: float, tp: float, quantity: float):
        self.log.info(f"TradeManager.buy: {entry}, {sl}, {tp}, {quantity}")
        trade = self.trade_factory.market_entry(entry, sl, tp, quantity)
        self.trades.append(trade)

        trade.submit()

    def on_order_event(self, order_event):
        # pass on the event to the trades and let them update their state
        self.log.debug(f"TradeManager.on_order_event: trades={self.trades}")
        for trade in self.trades:
            trade.on_order_event(order_event)
            if trade.finished.is_active or trade.error.is_active:
                self.log.info(f"TradeManager.on_order_event: {trade.id} is moved to finished_trades")
                self.trades.remove(trade)
                self.finished_trades.append(trade)
        pass

    def on_position_event(self, position_event):
        # pass on the event to the trades and let them update their state
        for trade in self.trades:
            trade.on_position_event(position_event)
            if trade.finished.is_active or trade.error.is_active:
                self.trades.remove(trade)
                self.finished_trades.append(trade)
        pass

