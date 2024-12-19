import typing
from builtins import bool
from dataclasses import field
from datetime import timedelta
from decimal import Decimal
import enum
import duckdb
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
from nautilus_trader.common.config import ImportableConfig
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.core.datetime import (
    dt_to_unix_nanos,
    maybe_unix_nanos_to_dt,
    unix_nanos_to_dt,
)
from nautilus_trader.core.data import Data
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_dt, format_iso8601
from nautilus_trader.model.data import DataType
from nautilus_trader.serialization.base import register_serializable_type

def unix_nanos_to_str(unix_nanos):
    return format_iso8601(unix_nanos_to_dt(unix_nanos))


# time series persistence and analysis
from influxdb_client.client.write.point import Point
from influxdb_client.client.influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import WriteOptions, WriteApi
from influxdb_client.domain.write_precision import WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from reactivex.scheduler import ThreadPoolScheduler

from questdb.ingress import Sender, IngressError, TimestampNanos, TimestampMicros
import sys
import datetime
from dataclasses import dataclass

from trade_manager import TradeManager
import utils
from put101.utils import TrackerMulti
from point_writer import PointWriter # type: ignore
from ingress_writer import IngressWriter # type: ignore
from portfolio_writer import PortfolioWriter
from events_writer import EventsWriter  # type: ignore
import importlib

class MyData(Data):
        """Entry Signal data."""
        def __init__(self, data_type, data, ts_event: int, ts_init: int):
            self.data_type=data_type
            self.data = data
            self._ts_event = ts_event
            self._ts_init = ts_init

        def __repr__(self):
            return f"MyData{self.data_type}(data={self.data})"
        
        @property
        def ts_event(self) -> int:
            """
            UNIX timestamp (nanoseconds) when the data event occurred.

            Returns
            -------
            int
            """
            return self._ts_event

        @property
        def ts_init(self) -> int:
            """
            UNIX timestamp (nanoseconds) when the object was initialized.

            Returns
            -------
            int
            """
            return self._ts_init

@dataclass  
class QuestDBConfig:
    conf: str = "http::addr=localhost:9000;"

@dataclass
class MainConfig:
    indicators: list[dict]  # List of indicators with class and params
    bb_params: list[tuple[int, float]]  # period  # std
    rsi_periods: list[int]  # RSI periods
    sl_pips: int
    tp_pips: int
    risk_reward: float
    
    # general
    instrument_id: str
    bar_type: str
    IDENTIFIER: str
    emulation_trigger: str = "NO_TRIGGER"
    manage_contingent_orders = True
    IGNORE_SINGLE_PRICE_BARS: bool = True
    # plotting, monitoring and statistics
    use_bokeh_plotting: bool = False
    write_price_data = True
    write_indicator_data = True
    bucket = "nautilus"
    environment: dict = field(default_factory=dict)
    questdb: QuestDBConfig = field(default_factory=QuestDBConfig)
    duckdb: str = "./nautilus.db"
    events_writer: dict = field(default_factory=dict)
    enable_influxdb: bool = True
    enable_questdb: bool = True

class PUT101StrategyConfig(StrategyConfig):
    main: MainConfig

class PUT101Strategy(Strategy):
    def __init__(self, config: PUT101StrategyConfig):
        super().__init__(config)
        self.log.debug('__init__ PUT101Strategy')
        self.IS_ABORTED = False
        
        # config basic parameters
        #self.conf: PUT101StrategyConfig = config
        self.conf = config.main
        self.bar_type: BarType = BarType.from_str(self.conf.bar_type)
        self.log.info(str(self.bar_type))
        self.instrument_id: InstrumentId = InstrumentId.from_str(
            self.conf.instrument_id)
        self.log.info(str(self.instrument_id))
        self.venue: Venue = self.instrument_id.venue
        self.emulation_trigger = TriggerType[self.conf.emulation_trigger]

        # other parameters
        self.max_dd = 0.05
        self.max_profit = 0.05

        # indicators
        self.all_indicators_ready = False
        self.indicators: list[Indicator] = []
        self.overlay_trackers: list[TrackerMulti] = []
        self.extra_trackers: list[TrackerMulti] = []

        # plotting styles
        self.overlay_styles: list = []
        self.extra_styles: list = []

        # concrete trackers
        self.portfolio_tracker: TrackerMulti = TrackerMulti(
            sub_indicator=utils.PortfolioIndicator(
                lambda: self.portfolio, self.venue),
            value_getters={
                "balance": lambda x: x.balance,
                "equity": lambda x: x.equity,
            },
        )

        for indicator_conf in self.conf.indicators:
            indicator_class = self._import_class(indicator_conf["class"])
            indicator = indicator_class(*indicator_conf["params"])
            self.indicators.append(indicator)
            if isinstance(indicator, BollingerBands):
                self.overlay_trackers.append(
                    TrackerMulti(indicator, value_getters={
                        "lower": lambda x: x.lower,
                        "middle": lambda x: x.middle,
                        "upper": lambda x: x.upper,
                    })
                )
            elif isinstance(indicator, RelativeStrengthIndex):
                self.extra_trackers.append(
                    TrackerMulti(indicator, value_getters={
                        "rsi": lambda x: x.value,
                    })
                )

        self.indicators.extend(self.overlay_trackers)
        self.indicators.extend(self.extra_trackers)

        self.took_position = False

        self.instrument: Instrument  # see on_start
        self.processed_bars: list[Bar] = []

        self.trade_manager = TradeManager(self, self.write_points)
        self.risk_manager = RiskManager(self)

        # Initialize writers
        self.client: InfluxDBClient = None
        self.write_api: WriteApi = None
        self.questdb: Sender = None
        self.point_writer: PointWriter = None
        self.ingress_writer: IngressWriter = None    
        self.portfolio_writer: PortfolioWriter = None
        self.events_writer: EventsWriter = None

    def _import_class(self, class_path: str):
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def influx_success(self, conf: tuple[str, str, str], data: str):
        self.log.debug(f"influx_success: Written batch: {conf}")
        return

    def influx_error(self, conf: tuple[str, str, str], data: str, exception: InfluxDBError):
        self.log.error(f"influx_error: Cannot write batch: {conf}, due: {exception}")
        return

    def influx_retry(self, conf: tuple[str, str, str], data: str, exception: InfluxDBError):
        self.log.error(f"influx_retry: Retryable error occurs for batch: {conf}, retry: {exception}")
        return

    def on_start(self):
        self.log.info("ON_START")
        
        # insert on_start
        self.db.execute('INSERT INTO events_str VALUES (NOW(), ?)', [str({'event': 'on_start'})] )

        if self.conf.enable_influxdb:
            token = self.conf.environment["INFLUX_TOKEN"]
            self.log.debug(f"INFLUX_TOKEN: {token}")

            self.client = InfluxDBClient(
                url="http://localhost:8086",
                token=token,
                org="main",
            )
            
            self.write_api = self.client.write_api(
                write_options=WriteOptions(
                    batch_size=10_000,
                    flush_interval=1000,
                    max_retries=0,
                    max_retry_delay=500,
                    max_retry_time=500,
                    exponential_base=2,
                    retry_interval=100,
                    max_close_wait=1_000,
                ),
                success_callback=self.influx_success,
                error_callback=self.influx_error,
                retry_callback=self.influx_retry,
            )
            self.point_writer = PointWriter(self.write_api, self.conf.bucket, self.log, self.conf.IDENTIFIER)
            self.portfolio_writer = PortfolioWriter(
                influx_write_api=self.write_api,
                questdb_sender=None,
                bucket=self.conf.bucket,
                logger=self.log,
                identifier=self.conf.IDENTIFIER
            )

        if self.conf.enable_questdb:
            self.questdb = Sender.from_conf(self.conf.questdb.conf)
            self.questdb.establish()
            self.ingress_writer = IngressWriter(self.questdb, self.log, self.conf.IDENTIFIER)
            self.portfolio_writer = PortfolioWriter(
                influx_write_api=None,
                questdb_sender=self.questdb,
                bucket=self.conf.bucket,
                logger=self.log,
                identifier=self.conf.IDENTIFIER
            )

        if self.conf.enable_influxdb or self.conf.enable_questdb:
            self.events_writer = EventsWriter(
                influx_write_api=self.write_api if self.conf.enable_influxdb else None,
                questdb_sender=self.questdb if self.conf.enable_questdb else None,
                bucket=self.conf.bucket,
                logger=self.log,
                identifier=self.conf.IDENTIFIER
            )

        self.instrument = self.cache.instrument(self.instrument_id)

        if self.instrument is None:
            msg = f"Could not find instrument for {self.instrument_id}"
            self.log.error(msg)
            self.abort(msg)
            return False

        self.subscribe_bars(self.bar_type)
        self.subscribe_data(DataType(MyData))
        
        self.risk_manager.on_start()
        

    def on_order_event(self, event: OrderEvent):
        self.log.debug(f"OrderEvent: {event}")
        if self.events_writer:
            self.events_writer.write_event_to_questdb(event)
            self.events_writer.write_event_to_influx(event)
        self.trade_manager.on_order_event(event)

    def on_position_event(self, event: PositionEvent):
        if self.events_writer:
            self.events_writer.write_event_to_questdb(event)
            self.events_writer.write_event_to_influx(event)
        self.trade_manager.on_position_event(event)

    def on_event(self, event: Event):
        if self.events_writer:
            self.events_writer.write_event_to_questdb(event)
            self.events_writer.write_event_to_influx(event)
    
    def on_data(self, data):
        if self.events_writer:
            if isinstance(data, MyData):
                self.events_writer.write_event_to_questdb(data)
                self.events_writer.write_event_to_influx(data)
            else:
                self.events_writer.write_event_to_questdb(data)
                self.events_writer.write_event_to_influx(data)
    
    def on_bar(self, bar: Bar) -> bool:
        """
        :param bar:
        :return: if true bar was processed, else false the bar was not processed
        """
        # debug log some objects
        if self.ingress_writer:
            self.ingress_writer.ingress_bar(bar, self.instrument_id.value, str(bar.bar_type), str(self.venue), self.conf.IDENTIFIER)

        for tracker in self.overlay_trackers:
            if tracker.initialized:
                for name, value in tracker.values.items():
                    if value:  # Check if there are any values
                        if self.ingress_writer:
                            self.ingress_writer.ingress_tracker(
                                self.instrument_id.value,
                                name,
                                value[-1],  # Get the last value
                                bar.ts_event
                            )

        if self.conf.IGNORE_SINGLE_PRICE_BARS and bar.is_single_price():
            return False

        # update indicators
        for i,indicator in enumerate(self.indicators):
            indicator.handle_bar(bar)

        for rsi in self.rsi_indicators:
            rsi.handle_bar(bar)

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

        # TRADING LOGIC
        cache: CacheFacade = self.cache
        portfolio: Portfolio = self.portfolio
        is_flat: bool = portfolio.is_flat(self.instrument_id)
        account: Account = portfolio.account(self.venue)
        balance: AccountBalance = account.balance(account.currencies()[0])
        balance_total: float = balance.total.as_double()

        if balance.total.as_double() < 10_000 * 0.70:
            msg = "balance too low, stopping strategy"
            self.log.error(msg)
            self.abort(msg)
            return False

        POINT_SIZE = float(self.instrument.price_increment)
        PIP_SIZE = 10 * POINT_SIZE

        MIN_SL_POINTS = 20
        ATR_SL_FACTOR = 1
        TP_FACTOR = 10

        SL_POINTS = ATR_SL_FACTOR * (50 / POINT_SIZE)
        SL_POINTS = max(SL_POINTS, MIN_SL_POINTS)

        RISK_PER_TRADE = self.max_dd / 2
        RISK = RISK_PER_TRADE * balance_total

        buy_signal = False
        sell_signal = False
        ts = maybe_unix_nanos_to_dt(bar.ts_event)

        if all(b.lower > bar.close.as_double() for b in self.bands):
            buy_signal = True
        if all(b.upper < bar.close.as_double() for b in self.bands):
            sell_signal = True

        if buy_signal or sell_signal:
            # send custom data event to nautilus
            val = "buy_signal" if buy_signal else "sell_signal"
            self.publish_data(DataType(MyData), MyData('entry_signal', val, bar.ts_event, bar.ts_event))

        SL_DIST = self.conf.sl_pips * PIP_SIZE
        if self.conf.risk_reward != 0:
            TP_DIST = SL_DIST * self.conf.risk_reward
        else:
            raise NotImplementedError("risk_reward cannot be 0")
        
        n_trades = len(self.trade_manager.trades)
        if is_flat and n_trades == 0:
            if buy_signal:
                self.log.info(f"SL_DIST: {SL_DIST}, TP_DIST: {TP_DIST}")
                entry = bar.close.as_double()
                sl = bar.close.as_double() - SL_DIST
                tp = bar.close.as_double() + TP_DIST
                qty = self.risk_manager.get_quantity_(entry, sl, tp, 0.05)
                self.trade_manager.buy(entry,sl,tp,qty)
                
            if sell_signal:
                self.log.info(f"SL_DIST: {SL_DIST}, TP_DIST: {TP_DIST}")
                entry = bar.close.as_double()
                sl = bar.close.as_double() + SL_DIST
                tp = bar.close.as_double() - TP_DIST
                qty = self.risk_manager.get_quantity_(entry, sl, tp, 0.05)        
                self.trade_manager.sell(entry,sl,tp,qty)

        # INFLUX
        if self.point_writer:
            portfolio_point = (
                Point("portfolio")
                .tag("strategy_id", self.conf.IDENTIFIER)
                .field("balance", float(self.portfolio_tracker.sub_indicator.balance))
                .field("equity", float(self.portfolio_tracker.sub_indicator.equity))
                .field("margin", float(self.portfolio_tracker.sub_indicator.margin))
                .field("positions_open_count", cache.positions_open_count())
                .field("positions_total_count", cache.positions_total_count())
                .field("orders_open_count", cache.orders_open_count())
                .field("orders_total_count", cache.orders_total_count())
                .time(bar.ts_event, WritePrecision.NS)
            )
            self.point_writer.write_points([portfolio_point])

            positions_open: list[Position] = cache.positions_open()
            for pos in positions_open:
                self.point_writer.write_position(bar, pos, self.conf.IDENTIFIER)

            for b in self.bands:
                point = (
                    Point(f"indicator_bollinger")
                    .tag("strategy_id", self.conf.IDENTIFIER)
                    .tag("parameters", str(b))
                    .field("lower", b.lower)
                    .field("middle", b.middle)
                    .field("upper", b.upper)
                    .time(bar.ts_event, WritePrecision.NS)
                )
                self.point_writer.write_points([point])
                
        if self.portfolio_writer:
            self.portfolio_writer.write_portfolio_to_influx(self.portfolio, self.cache, bar)
            self.portfolio_writer.write_positions_to_influx(bar, self.cache.positions_open())
            self.portfolio_writer.write_portfolio_to_questdb(self.portfolio, self.cache, bar)
            self.portfolio_writer.write_positions_to_questdb(bar, self.cache.positions_open())
        return True

    def make_point(self, event: PositionEvent):
        event_type = type(event).__name__
        json_body = {
            "measurement": "position_events",
            "tags": {
                "trader_id": event.trader_id,
                "strategy_id": self.conf.IDENTIFIER,
                "instrument_id": event.instrument_id,
                "position_id": event.position_id,
            },
            "time": event.ts_event,
            "fields": {
                "event_type": event_type,
                "entry": str(event.entry),
                "side": str(event.side),
                "signed_qty": float(event.signed_qty),
                "quantity": float(event.quantity),
                "peak_qty": float(event.peak_qty),
                "last_qty": float(event.last_qty),
                "last_px": float(event.last_px),
                "avg_px_open": float(event.avg_px_open),
                "avg_px_close": event.avg_px_close if hasattr(event, 'avg_px_close') else None,
                "realized_pnl": float(event.realized_pnl),
                "unrealized_pnl": float(event.unrealized_pnl),
            }
        }
        return json_body

    def write_points(self, points):
        if self.IS_ABORTED:
            return
        try:
            self.write_api.write(
                bucket=self.conf.bucket,
                record=points,
            )
        except InfluxDBError as e:
            self.log.error(f"Error writing to influx: {e}")
            raise e

    def abort(self, msg):
        """
        abort the strategy with a reason
        :return:
        """
        if self.IS_ABORTED:
            return
        self.IS_ABORTED = True
        print("ABORT: ", msg)
        self.log.error("ABORT: " + msg)
        self.stop()

    def on_stop(self):
        if not self.IS_ABORTED:
            self.log.info("on_stop")
            if self.client:
                self.log.info("stopping influx client")
                self.client.close()
                self.log.info("influx client stopped")

            if self.questdb:
                self.log.info("closing questdb")
                self.questdb.close()
                self.questdb = None
                self.log.info("questdb closed")        

            self.log.info("closing duckdb")
            self.db.close()
            self.log.info("duckdb closed")
    
    def on_dispose(self):
        self.log.info("on_dispose")

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
                f"Cannot partially close position (the position is already closed), {
                    position}."
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
        
        

class RiskManager:
    def __init__(self, strategy: "PUT101Strategy"):
        self.log = strategy.log
        self.log.info("RiskManager.__init__")
        self.strategy = strategy
        
    
    def on_start(self):
        self.log.info("RiskManager.on_start") 
        
    def get_quantity_(self, entry: float, sl: float, tp: float, risk: float):
        """
        Calculate position size based on risk percentage
        Parameters:
        - entry: Entry price
        - sl: Stop loss price
        - risk_percentage: Risk as decimal (e.g., 0.01 for 1%)
        """
        self.log.info(f"RiskManager.get_quantity_: entry={entry}, sl={sl}, tp={tp}, risk={risk}")
        account:Account = self.strategy.portfolio.account(self.strategy.venue)
        balance = account.balance(account.currencies()[0])
        balance_total = balance.total.as_double()
        
        if entry == 0 or sl == 0 or tp == 0 or risk == 0 or (entry == sl):
            self.log.error("Invalid entry, sl, tp or risk")
            return 0
        
        risk_amount = balance_total * risk
        self.log.info(f"RiskManager.get_quantity_: risk_amount={risk_amount}")
        i: Instrument = self.strategy.instrument
        
        # Calculate pip value and risk per pip
        pip_value = i.lot_size.as_double() * i.price_increment.as_double()
        self.log.info(f"RiskManager.get_quantity_: pip_value={pip_value}")
        
        # Calculate stop loss distance in pips
        sl_distance = abs(entry - sl) / i.price_increment.as_double()
        self.log.info(f"RiskManager.get_quantity_: sl_distance={sl_distance}")
        # Calculate required position size in base units
        raw_units = (risk_amount / (sl_distance * pip_value)) * i.lot_size.as_double()
        self.log.info(f"RiskManager.get_quantity_: raw_units={raw_units}")
        
        # Round to instrument's size increment
        units = round(raw_units / i.size_increment.as_double()) * i.size_increment.as_double()
        self.log.info(f"RiskManager.get_quantity_: units={units}")
        
        # Ensure within instrument limits
        units = max(i.min_quantity.as_double(), 
                   min(units, i.max_quantity.as_double()))
        
        lots = units / i.lot_size.as_double()
        
        self.log.info(f"Risk calculation: Balance Total={balance_total}, "
                     f"Risk Amount={risk_amount}, Units={units}, Lots={lots}")
        
        return i.make_qty(units)