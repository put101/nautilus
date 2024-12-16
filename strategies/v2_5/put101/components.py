import enum
from datetime import timedelta

from nautilus_trader.core.nautilus_pyo3 import OrderSide, TimeInForce, OrderType, PositionId
from nautilus_trader.model.events import OrderEvent, OrderRejected, OrderAccepted, OrderFilled, PositionOpened, PositionClosed
from nautilus_trader.model.orders import OrderList, Order
from nautilus_trader.model.position import Position
from nautilus_trader.portfolio import Portfolio
from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.objects import Quantity, AccountBalance
from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.model.instruments.base import Instrument
from statemachine import StateMachine, State
from statemachine.exceptions import  TransitionNotAllowed


import strategies.base as base

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

class SimpleTrade(Trade):

    def __init__(self, factory, order_list: OrderList):
        super().__init__()
        self.factory = factory
        self.strategy: base.PUT101Strategy = factory.strategy
        self.order_list: OrderList = order_list
        self.position_id: PositionId | None = None

    created = State('Created', initial=True)
    submitted = State('Submitted')

    entered = State('Entered')

    error = State('Error', final=True)

    finished = State('Finished', final=True)

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
                    self.strategy.log.error(f"SimpleTrade.on_order_event: OrderRejected({event.client_order_id})")

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
                self.strategy.log.error(f"SimpleTrade.on_position_opened: PositionOpened({event.position_id})")


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
    def __init__(self, strategy: base.PUT101Strategy):
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
            expire_time=strategy.clock.utc_now() + timedelta(seconds=self.expire_seconds),
            entry_price=strategy.instrument.make_price(entry),
            entry_trigger_price=strategy.instrument.make_price(entry),
            sl_trigger_price=strategy.instrument.make_price(sl),
            tp_price=strategy.instrument.make_price(tp),
            entry_order_type=OrderType.MARKET_IF_TOUCHED,
            emulation_trigger=strategy.emulation_trigger,
        )

        trade = SimpleTrade(strategy, order_list)
        return trade


class TradeManager:
    def __init__(self, strategy):
        self.strategy: base.PUT101Strategy = strategy
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
        self.high_mark = strategy.account.balance(strategy.account.currencies()[0]).total.as_double()
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

