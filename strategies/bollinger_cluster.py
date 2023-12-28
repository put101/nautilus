# define bollinger band strategy
# then try to visualize it
# try to visualize clusters as well
from builtins import bool
from datetime import timedelta

from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.core.rust.model import OrderSide, TimeInForce, OrderType, TriggerType
from nautilus_trader.indicators.base.indicator import Indicator
from nautilus_trader.indicators.bollinger_bands import BollingerBands
from nautilus_trader.model.data import BarType, Bar
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.identifiers import Venue, InstrumentId
from nautilus_trader.model.objects import Quantity, Currency
from nautilus_trader.model.orders import OrderList
from nautilus_trader.portfolio import Portfolio
from nautilus_trader.trading import Strategy
from nautilus_trader.trading.strategy import StrategyConfig

import utils
from indicators import TrackerMulti


class BollingerClusterConfig(StrategyConfig):
    bb_params: list[tuple[int, float]]
    instrument_id: str
    bar_type: str
    emulation_trigger: str = "NO_TRIGGER"

class BollingerCluster(Strategy):
    def __init__(self, config: BollingerClusterConfig):
        super().__init__(config)
        self.unrealized = []
        self.unrealized_timestamps = []
        self.use_debugstop = False
        self.myconfig = config
        self.bar_type: BarType = BarType.from_str(config.bar_type)
        self.bands: list[BollingerBands] = [BollingerBands(bb[0], bb[1]) for bb in self.myconfig.bb_params]
        self.trackers: list[TrackerMulti] = []
        self.instrument_id: InstrumentId = InstrumentId.from_str(config.instrument_id)
        self.venue: Venue = self.instrument_id.venue
        self.emulation_trigger = TriggerType[config.emulation_trigger]

        for b in self.bands:
            self.trackers.append(TrackerMulti(b, {
                "lower": lambda: b.lower,
                "middle": lambda: b.middle,
                "upper": lambda: b.upper
            }))

        self.indicators: list[Indicator] = []
        self.indicators.extend(self.trackers)
        self.balances_timestamps = []
        self.balances = []

        self.temp_debug = []
        self.debug_max = 10
        self.debug_i = 0

        self.took_position = False

        self.instrument: Instrument | None = None # see on_start

        print("initialized strategy")

    def on_start(self):

        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.instrument_id}")
            self.stop()
            return

        self.log.info("starting strategy")
        self.subscribe_bars(self.bar_type)
        self.log.info("started strategy")
        pass

    def on_bar(self, bar: Bar):
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
                return

        portfolio: Portfolio = self.portfolio
        order_factory: OrderFactory = self.order_factory

        isFlat: bool = portfolio.is_flat(self.instrument_id)

        SL_POINTS = 500
        TP_POINTS = 100
        POINT_SIZE = 0.00001
        PIP_SIZE = 10 * POINT_SIZE

        # Portfolio tracking
        portfolio:Portfolio = self.portfolio
        account:Account = portfolio.account(self.venue)
        account.balance_total()
        self.balances_timestamps.append(bar.ts_event)
        self.balances.append(account.balance_total())
        self.unrealized_timestamps.append(bar.ts_event)
        self.unrealized.append(portfolio.unrealized_pnls(self.venue))

        if isFlat:
            if self.bands[0].lower > bar.close.as_double():
                self.buy(bar.close.as_double(), bar.close.as_double() - SL_POINTS*POINT_SIZE, bar.close.as_double() + TP_POINTS*POINT_SIZE, 1000)
            elif self.bands[0].upper < bar.close.as_double():
                self.sell(bar.close.as_double(), bar.close.as_double() + SL_POINTS*POINT_SIZE, bar.close.as_double() - TP_POINTS*POINT_SIZE, 1000)
        else:
            self.took_position = True

        # debug log some objects
        self.debug_i += 1
        pass

    def on_stop(self):
        self.log.info("stopping strategy")
        pass

    def draw(self, fig):
        for tracker in self.trackers:
            fig = utils.add_multiline_indicator(fig, tracker, "white")

        return fig


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
            entry_order_type=OrderType.LIMIT_IF_TOUCHED,
            emulation_trigger=self.emulation_trigger,
        )

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
            entry_order_type=OrderType.LIMIT_IF_TOUCHED,
            emulation_trigger=self.emulation_trigger,
        )

        self.submit_order_list(order_list)