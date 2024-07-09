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

from datetime import timedelta
from influxdb_client import Point

from trade import SimpleTrade

class TradeFactory:
    def __init__(self, strategy):
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

        trade = SimpleTrade(self.strategy, order_list)
        return trade
