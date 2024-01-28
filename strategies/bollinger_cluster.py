import datetime
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
from nautilus_trader.indicators.atr import  AverageTrueRange
from nautilus_trader.core.datetime import dt_to_unix_nanos, maybe_unix_nanos_to_dt, unix_nanos_to_dt


import put101.utils as utils
import put101.vizz as vizz
from put101.indicators import TrackerMulti

percent: TypeAlias = float

class BollingerClusterConfig(StrategyConfig):
    instrument_id: str
    bar_type: str
    bb_params: list[tuple[
        int,  # period
        float  # std
    ]]

    USE_TRADING_HOURS: bool = True
    TRADING_SESSIONS: list[tuple[int, int]] = field(default_factory=lambda: [(0, 24)])
    PARTIAL_RATIO: float | None = None

    emulation_trigger: str = "NO_TRIGGER"
    manage_contingent_orders = True



class BollingerCluster(Strategy):
    def __init__(self, config: BollingerClusterConfig):
        super().__init__(config)
        self.unrealized = []
        self.unrealized_timestamps = []
        self.use_debugstop = False
        self.myconfig = config
        self.bar_type: BarType = BarType.from_str(config.bar_type)

        self.bands: list[BollingerBands] = [BollingerBands(
            period, std) for period, std in self.myconfig.bb_params]
        self.overlay_trackers: list[TrackerMulti] = []
        self.overlay_styles: list[vizz.LineIndicatorStyle] = []
        self.extra_trackers: list[TrackerMulti] = []
        self.extra_styles: list[vizz.LineIndicatorStyle] = []
        self.indicators: list[Indicator] = []
        

        self.instrument_id: InstrumentId = InstrumentId.from_str(
            config.instrument_id)
        self.venue: Venue = self.instrument_id.venue
        self.emulation_trigger = TriggerType[config.emulation_trigger]

        # PORTFOLIO TRACKING
        self.portfolio_tracker: TrackerMulti = TrackerMulti(
            sub_indicator=utils.PortfolioIndicator(lambda: self.portfolio, self.venue),
            value_getters={"balance": lambda x: x.balance,
                           "equity": lambda x: x.equity,
                           #"margin_pct": lambda x: x.margin_pct,
                           })
        self.indicators.append(self.portfolio_tracker)


        bollinger_getters = {
                "lower": lambda x: x.lower,
                "middle": lambda x: x.middle,
                "upper": lambda x: x.upper
        }

        for b in self.bands:
            self.overlay_trackers.append(TrackerMulti(b, value_getters=bollinger_getters))
            self.overlay_styles.append(vizz.LineIndicatorStyle("blue",0.5,2))

        from nautilus_trader.indicators.average.ma_factory import MovingAverageFactory, MovingAverageType
        ma_getters = {
            "ma": lambda x: x.value
        }

        self.ema_slow = MovingAverageFactory.create(50, MovingAverageType.EXPONENTIAL)
        self.overlay_trackers.append(TrackerMulti(self.ema_slow, value_getters=ma_getters))
        self.overlay_styles.append(vizz.LineIndicatorStyle("black", 0.5, 2))

        self.ema_fast = MovingAverageFactory.create(30, MovingAverageType.EXPONENTIAL)
        self.overlay_trackers.append(TrackerMulti(self.ema_fast, value_getters=ma_getters))
        self.overlay_styles.append(vizz.LineIndicatorStyle("red", 0.5, 2))

        self.atr = AverageTrueRange(7)
        self.atr_tracker = TrackerMulti(self.atr, value_getters={"atr": lambda x: x.value})
        self.indicators.append(self.atr_tracker)

        for i in [
            RelativeStrengthIndex(14)]:
            self.extra_trackers.append(TrackerMulti(i, value_getters={"value": lambda x: x.value}))
            self.extra_styles.append(vizz.LineIndicatorStyle("green",0.5,2))
        self.indicators.extend(self.extra_trackers)



        self.indicators.extend(self.overlay_trackers)

        self.balances_timestamps = []
        self.balances = []

        self.temp_debug = []
        self.debug_max = 10
        self.debug_i = 0

        self.took_position = False

        self.instrument: Instrument | None = None  # see on_start
        self.processed_bars: list[Bar] = []

        self.manage_positions = []


    def get_main_plottable_indicators(self) -> tuple[list[TrackerMulti], list[vizz.LineIndicatorStyle]]:
        return (self.overlay_trackers, self.overlay_styles)

    def get_extra_plots(self) -> list[tuple[list[TrackerMulti], list[vizz.LineIndicatorStyle]]]:
        return [(vizz.PlotConfig(title="Portfolio Tracker"), [self.portfolio_tracker], [vizz.LineIndicatorStyle("blue", 0.5, 2)]),
                (vizz.PlotConfig(title="Extra Trackers"), self.extra_trackers, self.extra_styles),
                (vizz.PlotConfig(title=f"ATR {self.atr.period}"), [self.atr_tracker], [vizz.LineIndicatorStyle("green", 0.5, 2)]),
                ]

    @property
    def bars(self) -> list[Bar]:
        return self.processed_bars

    def on_start(self):

        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(
                f"Could not find instrument for {self.instrument_id}")
            self.stop()
            return

        self.log.info("starting strategy")
        self.subscribe_bars(self.bar_type)
        self.log.info("started strategy")
        pass

    def on_event(self, event: Event):

        if isinstance(event, OrderEvent):
            self.log.info(f"OrderEvent: {event}")


        if isinstance(event, PositionEvent):
            self.log.info(f"PositionEvent: {event}")


        return

    def on_bar(self, bar: Bar):
        # debug log some objects
        self.debug_i += 1

        if self.use_debugstop and self.debug_i > self.debug_max:
            self.stop()
            return

        if bar.is_single_price():
            return

        # update indicators
        for indicator in self.indicators:
            indicator.handle_bar(bar)

        for indicator in self.indicators:
            if not indicator.initialized:
                self.log.debug("indicator not initialized, skipping bar processing: " + str(indicator))
                return

        self.processed_bars.append(bar)

        portfolio: Portfolio = self.portfolio
        account: Account = portfolio.account(self.venue)
        balance: AccountBalance = account.balance(account.currencies()[0])
        cache: CacheFacade = self.cache
        balance_total: float = balance.total.as_double()
        balance_free: float = balance.free.as_double()
        balance_locked: float = balance.locked.as_double()

        order_factory: OrderFactory = self.order_factory
        is_flat: bool = portfolio.is_flat(self.instrument_id)


        self.max_dd = 0.02
        self.max_profit = 0.02

        if balance.total.as_double() < 10_000 * 0.90:
            self.log.error("balance too low, stopping strategy")
            self.stop()

        if not is_flat:
            pnl = portfolio.unrealized_pnl(self.instrument_id)
            cur_max_dd = balance.total.as_double() * self.max_dd
            min_pnl = -abs(cur_max_dd)
            if pnl and pnl.as_double() < min_pnl:
                self.log.error(f"Max DD reached: {pnl.as_double()} < {min_pnl}, closing all positions")
                self.close_all_positions(self.instrument_id)

            cur_max_profit = balance.total.as_double() * self.max_profit
            max_pnl = abs(cur_max_profit)
            if pnl and pnl.as_double() > max_pnl:
                if not self.config.PARTIAL_RATIO:
                    self.log.warn(f"cannot close partials, no PARTIAL_RATIO set")
                self.log.error(f"Max PNL reached: {pnl.as_double()} > {max_pnl}, closing partial positions")
                #self.close_all_positions(self.instrument_id)
                positions_open: list[Position] = self.cache.positions_open(
                    venue=None,  # Faster query filtering
                    instrument_id=self.instrument_id,
                    side=PositionSide.NO_POSITION_SIDE
                )
                for pos in positions_open:
                    if self.config.PARTIAL_RATIO is not None:
                        partial_quantity = pos.quantity * self.config.PARTIAL_RATIO

                    self.close_partial_position(pos,
                                                partial_quantity,
                                                tags=f"PARTIAL:MAX_PNL_REACHED, PARTIAL_RATIO: {str(self.config.PARTIAL_RATIO)}")

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


        #self.log.info("last tick: " + str(cache.quote_ticks(self.instrument_id)[-1]))

        qty = utils.RiskCalculator.qty_from_risk(entry=bar.close.as_double(),
                                                 exit=bar.close.as_double() + SL_POINTS * float(self.instrument.price_increment),
                                                 risk=RISK,
                                                 ins=self.instrument)

        buy_signal = False
        sell_signal = False


        # SIGNAL COMPOSITION


        ts = maybe_unix_nanos_to_dt(bar.ts_event)

        # trading hours
        USE_TRADING_HOURS: bool = bool(self.config.USE_TRADING_HOURS)
        TRADING_HOURS_START = 8
        TRADING_HOURS_END = 17

        if USE_TRADING_HOURS and not utils.in_session_hours(self.config.TRADING_SESSIONS, ts):
            return

        up_trend = self.ema_fast.value > self.ema_slow.value
        down_trend = self.ema_fast.value < self.ema_slow.value

        if up_trend and self.bands[0].lower > bar.close.as_double():
            buy_signal = True
        if down_trend and self.bands[0].upper < bar.close.as_double():
            sell_signal = True



        # SIGNAL EXECUTION

        if is_flat:
            if buy_signal:
                self.buy(bar.close.as_double(), bar.close.as_double(
                ) - SL_POINTS*POINT_SIZE, bar.close.as_double() + TP_POINTS*POINT_SIZE, qty)

            if sell_signal:
                self.sell(bar.close.as_double(), bar.close.as_double(
                ) + SL_POINTS*POINT_SIZE, bar.close.as_double() - TP_POINTS*POINT_SIZE, qty)


        pass

    def on_stop(self):
        self.log.info("stopping strategy")
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

    def sell(self,  entry: float, sl: float, tp: float, quantity: float) -> None:

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

    def close_partial_position(self,  position: Position, partial_quantity: Quantity | Decimal | float, client_id=None, tags=None):
        """
        Partially close the given position.

        Parameters:
        - position (Position): The position to partially close.
        - partial_quantity (Quantity): The quantity of the position to close.
        - client_id (ClientId, optional): The specific client ID for the command. If None, then inferred from the venue in the instrument ID.
        - tags (str, optional): Tags for the market order closing the position.
        """

        if position.is_closed:
            self.log.error(f"Cannot partially close position (the position is already closed), {position}.")
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
        self.submit_order(order, position_id=position.id,  client_id=client_id)

                