
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


def total_commission(pos: Position) -> float:
    total_commissions = sum(
        (commission for commission in pos.commissions()), Money(0, pos.base_currency)
    )
    return float(total_commissions)


class PortfolioIndicator(Indicator):
    def __init__(self, portfolio_getter: callable, venue):
        super().__init__(["portfolio"])
        self.portfolio_getter = portfolio_getter
        self.venue = venue
        self.balance: float = 0
        self.unrealized_pnl: float = 0
        self.equity: float = 0
        self.margin: float = 0
        self.margin_pct: float = 0
        self.free: float = 0

    @property
    def initialized(self):
        return self.portfolio_getter() is not None and self.venue is not None

    @property
    def has_inputs(self):
        return self.portfolio_getter().unrealized_pnls(self.venue) is not None

    def handle_bar(self, bar: Bar):
        p: Portfolio = self.portfolio_getter()
        a: Account = p.account(self.venue)
        a_currency: Currency = a.currencies()[0]

        # balance
        self.balance: float = a.balance(a.currencies()[0]).total.as_double()

        # unrealized pnl
        unreal_pnl_dict = p.unrealized_pnls(self.venue)
        self.unrealized_pnl = unreal_pnl_dict.get(
            a_currency, Money(0, a_currency)
        ).as_double()
        # equity
        self.equity = self.balance + self.unrealized_pnl

        # margin
        self.margin = 0
        if a.is_margin_account:
            am: MarginAccount = a
            # {}
            # {InstrumentId('EURUSD.SIM_EIGHTCAP'): MarginBalance(initial=54.89 USD, maintenance=0.00 USD, instrument_id=EURUSD.SIM_EIGHTCAP)}

            for k, v in am.margins().items():
                self.margin += v.initial.as_double()

        # margin pct
        if self.equity > 0:
            self.margin_pct = self.equity - self.margin
        else:
            self.margin_pct = 0



from questdb.ingress import Sender, IngressError, TimestampNanos
import sys
import datetime

def example(conf):
    try:
        with Sender.from_conf(conf) as sender:
            # Record with provided designated timestamp (using the 'at' param)
            # Notice the designated timestamp is expected in Nanoseconds,
            # but timestamps in other columns are expected in Microseconds. 
            # The API provides convenient functions
            for i in range(10):
                sender.row(
                    'trades',
                    symbols={
                        'pair': 'USDGBP',
                        'type': 'buy'},
                    columns={
                        'traded_price': 0.83,
                        'limit_price': 0.84,
                        'qty': 100,
                        'some_string': 'hello',
                        'more_strings': str(['world', 'foo', 'ba']),
                        'traded_ts': datetime.datetime(
                            2022, 8, 6, 7, 35, 23, 189062,
                            tzinfo=datetime.timezone.utc)},
                    at=TimestampNanos.now())

            # You can call `sender.row` multiple times inside the same `with`
            # block. The client will buffer the rows and send them in batches.

            # You can flush manually at any point.
            sender.flush()

            # If you don't flush manually, the client will flush automatically
            # when a row is added and either:
            #   * The buffer contains 75000 rows (if HTTP) or 600 rows (if TCP)
            #   * The last flush was more than 1000ms ago.
            # Auto-flushing can be customized via the `auto_flush_..` params.

        # Any remaining pending rows will be sent when the `with` block ends.

    except IngressError as e:
        raise e
       

 