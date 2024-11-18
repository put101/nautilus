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
from datetime import timedelta

from .trade_factory import TradeFactory
from .trade import SimpleTrade

class TradeManager:
    def __init__(self, strategy, write_points):
        self.strategy = strategy
        self.write_points = write_points
        self.log = self.strategy.log
        self.cache: CacheFacade = strategy.cache
        self.trade_factory = TradeFactory(strategy, write_points)
        self.trades: list[SimpleTrade] = []
        self.finished_trades: list[SimpleTrade] = []

    def number_active_trades(self):
        return len(self.trades)

    def buy(self, entry: float, sl: float, tp: float, quantity: float):
        self.log.info(f"TradeManager.buy: {entry}, {sl}, {tp}, {quantity}")
        trade = self.trade_factory.market_entry(entry, sl, tp, quantity)
        self.trades.append(trade)

        trade.submit()

    def sell(self, entry: float, sl: float, tp: float, quantity: float):
        self.log.info(f"TradeManager.sell: {entry}, {sl}, {tp}, {quantity}")
        trade = self.trade_factory.market_entry(entry, sl, tp, quantity)
        self.trades.append(trade)

        trade.submit()

    def on_order_event(self, order_event):
        # pass on the event to the trades and let them update their state
        self.log.debug(f"TradeManager.on_order_event: trades={self.trades}")
        for trade in self.trades:
            trade.on_order_event(order_event)
            if trade.state_finished.is_active or trade.state_error.is_active:
                self.log.info(f"TradeManager.on_order_event: {trade.order_id} is moved to finished_trades")
                self.trades.remove(trade)
                self.finished_trades.append(trade)
        pass

    def on_position_event(self, position_event):
        # pass on the event to the trades and let them update their state
        for trade in self.trades:
            trade.on_position_event(position_event)
            if trade.state_finished.is_active or trade.state_error.is_active:
                self.trades.remove(trade)
                self.finished_trades.append(trade)
        pass

