from influxdb_client import Point
from influxdb_client.client.write_api import WriteApi
from influxdb_client.domain.write_precision import WritePrecision
from questdb.ingress import Sender, IngressError
from nautilus_trader.portfolio import Portfolio
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position
from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.identifiers import InstrumentId

class PortfolioWriter:
    def __init__(self, influx_write_api: WriteApi, questdb_sender: Sender, bucket: str, logger, identifier: str):
        self.influx_write_api = influx_write_api
        self.questdb_sender = questdb_sender
        self.bucket = bucket
        self.logger = logger
        self.identifier = identifier

    def write_portfolio_to_influx(self, portfolio: Portfolio, cache: CacheFacade, bar: Bar):
        # Writes portfolio data to InfluxDB
        portfolio_point = (
            Point("portfolio")
            .tag("strategy_id", self.identifier)
            .field("balance", float(portfolio.balance))
            .field("equity", float(portfolio.equity))
            .field("margin", float(portfolio.margin))
            .field("positions_open_count", cache.positions_open_count())
            .field("positions_total_count", cache.positions_total_count())
            .field("orders_open_count", cache.orders_open_count())
            .field("orders_total_count", cache.orders_total_count())
            .time(bar.ts_event, WritePrecision.NS)
        )
        self.influx_write_api.write(self.bucket, record=portfolio_point)

    def write_positions_to_influx(self, bar: Bar, positions: list[Position]):
        # Writes position data to InfluxDB
        for pos in positions:
            position_data = (
                Point("position")
                .tag("strategy_id", self.identifier)
                .tag("position_id", pos.id.value)
                .field("instrument_id", pos.instrument_id.value)
                .field("side", pos.side.value)
                .field("quantity", pos.quantity.as_double())
                .field("unrealized_pnl", pos.unrealized_pnl(bar.close).as_double())
                .field("sum_commissions", sum(c.as_double() for c in pos.commissions()))
                .time(bar.ts_event, WritePrecision.NS)
            )
            self.influx_write_api.write(self.bucket, record=position_data)

    def write_portfolio_to_questdb(self, portfolio: Portfolio, cache: CacheFacade, bar: Bar):
        # Writes portfolio data to QuestDB
        try:
            self.questdb_sender.row(
                'portfolio',
                symbols={
                    'strategy_id': self.identifier,
                },
                columns={
                    'balance': float(portfolio.balance),
                    'equity': float(portfolio.equity),
                    'margin': float(portfolio.margin),
                    'positions_open_count': cache.positions_open_count(),
                    'positions_total_count': cache.positions_total_count(),
                    'orders_open_count': cache.orders_open_count(),
                    'orders_total_count': cache.orders_total_count(),
                },
                at=bar.ts_event
            )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"write_portfolio_to_questdb cannot write to questdb: {e}")

    def write_positions_to_questdb(self, bar: Bar, positions: list[Position]):
        # Writes position data to QuestDB
        try:
            for pos in positions:
                self.questdb_sender.row(
                    'positions',
                    symbols={
                        'strategy_id': self.identifier,
                        'position_id': pos.id.value,
                    },
                    columns={
                        'instrument_id': pos.instrument_id.value,
                        'side': pos.side.value,
                        'quantity': pos.quantity.as_double(),
                        'unrealized_pnl': pos.unrealized_pnl(bar.close).as_double(),
                        'sum_commissions': sum(c.as_double() for c in pos.commissions()),
                    },
                    at=bar.ts_event
                )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"write_positions_to_questdb cannot write to questdb: {e}")
