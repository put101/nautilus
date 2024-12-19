from influxdb_client import Point
from influxdb_client.client.write_api import WriteApi
from influxdb_client.domain.write_precision import WritePrecision
from questdb.ingress import Sender, IngressError
from nautilus_trader.core.message import Event
from nautilus_trader.core.datetime import unix_nanos_to_dt
import datetime

class EventsWriter:
    def __init__(self, influx_write_api: WriteApi, questdb_sender: Sender, bucket: str, logger, identifier: str):
        self.influx_write_api = influx_write_api
        self.questdb_sender = questdb_sender
        self.bucket = bucket
        self.logger = logger
        self.identifier = identifier

    def write_event_to_influx(self, event: Event):
        # Writes event data to InfluxDB
        event_point = (
            Point("events")
            .tag("identifier", self.identifier)
            .tag("event_type", type(event).__name__)
            .field("event", str(event))
            .field("real_time_ts", unix_nanos_to_dt(int(datetime.datetime.now().timestamp() * 1e9)))
            .field("meta", "meta")  # todo: if needed
            .time(event.ts_event, WritePrecision.NS)
        )
        self.influx_write_api.write(self.bucket, record=event_point)

    def write_event_to_questdb(self, event: Event):
        # Writes event data to QuestDB
        real_time_ns = int(datetime.datetime.now().timestamp() * 1e9)
        try:
            self.questdb_sender.row(
                'events',
                symbols={
                    'identifier': self.identifier,
                    'event_type': type(event).__name__,
                },
                columns={
                    'event': str(event),
                    'real_time_ts': unix_nanos_to_dt(real_time_ns),
                    'meta': "meta"  # todo: if needed
                },
                at=unix_nanos_to_dt(event.ts_event)
            )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"write_event_to_questdb cannot write to questdb: {e}")
