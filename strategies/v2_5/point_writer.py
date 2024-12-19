from influxdb_client.client.write.point import Point
from influxdb_client.client.write_api import WriteApi
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.domain.write_precision import WritePrecision
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position
from nautilus_trader.model.events import PositionEvent

class PointWriter:
    def __init__(self, write_api: WriteApi, bucket: str, logger, identifier):
        self.write_api = write_api
        self.bucket = bucket
        self.logger = logger
        self.identifier:str = identifier
        self.logger.info(f"PointWriter initialized with identifier: {self.identifier}")

    def write_points(self, points):
        # Writes points to InfluxDB
        try:
            self.write_api.write(bucket=self.bucket, record=points)
        except InfluxDBError as e:
            self.logger.error(f"Error writing to influx: {e}")
            raise e

    def make_point(self, event: PositionEvent):
        # Creates a point for position events
        event_type = type(event).__name__
        json_body = {
            "measurement": "position_events",
            "tags": {
                "instrument_id": event.instrument_id,
                "position_id": event.position_id,
                "identifier": self.identifier,
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
        self.logger.info(f"PointWriter.make_point: {json_body}")
        return json_body

    def write_position(self, bar: Bar, position: Position, strategy_id: str):
        # Writes position data to InfluxDB
        position_data = (
            Point("position")
            .tag("strategy_id", strategy_id)
            .tag("position_id", position.id.value)
            .field("instrument_id", position.instrument_id.value)
            .field("side", position.side.value)
            .field("quantity", position.quantity.as_double())
            .field("unrealized_pnl", position.unrealized_pnl(bar.close).as_double())
            .field("sum_commissions", sum(c.as_double() for c in position.commissions()))
            .time(bar.ts_event, WritePrecision.NS)
        )
        self.write_points([position_data])

    """
    def write_position(self, bar: Bar, position: Position):

        position_data = (
            Point("position")
            .tag("strategy_id", self.conf.IDENTIFIER)
            .tag("position_id", position.id.value)
            .field("instrument_id", position.instrument_id.value)
            .field("side", position.side.value)
            .field("quantity", position.quantity.as_double())
            .field("unrealized_pnl", position.unrealized_pnl(bar.close).as_double())
            .field("commission", utils.total_commission(position))
            .time(bar.ts_event, WritePrecision.NS)
        )

        self.write_points([position_data])
    """
