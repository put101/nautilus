from questdb.ingress import Sender, IngressError
from nautilus_trader.model.data import Bar
from nautilus_trader.core.message import Event
from nautilus_trader.core.datetime import unix_nanos_to_dt
import datetime

class IngressWriter:
    def __init__(self, sender: Sender, logger):
        self.sender = sender
        self.logger = logger

    def ingress_tracker(self, instrument_id: str, name: str, value: float, ts: int, identifier: str):
        try:
            self.sender.row(
                'indicators',
                symbols={
                    'instrument_id': instrument_id,
                    'id': identifier,
                    'indicator': name
                },
                columns={
                    'value': value,
                    'real_time_ts': unix_nanos_to_dt()
                },
                at=unix_nanos_to_dt(ts)
            )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"ingress_indicator cannot write to questdb: {e}")

    def ingress_event(self, event: Event, instrument_id: str, venue: str, identifier: str):
        real_time_ns = int(datetime.datetime.now().timestamp() * 1e9)
        try:
            self.sender.row(
                'events',
                symbols={
                    'symbol': instrument_id,
                    'event_type': type(event).__name__,
                    'venue': venue,
                    'identifier': identifier,
                    'event': str(event),
                },
                columns={
                    'real_time_ts': unix_nanos_to_dt(real_time_ns),
                },
                at=unix_nanos_to_dt(event.ts_event)
            )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"ingress_event cannot write to questdb: {e}")

    def ingress_bar(self, bar: Bar, instrument_id: str, bar_type: str, venue: str, identifier: str):
        try:
            self.sender.row(
                'bars',
                symbols={
                    'symbol': instrument_id,
                    'bar_type': bar_type,
                    'venue': venue,
                },
                columns={
                    'close': bar.close.as_double(),
                    'open': bar.open.as_double(),
                    'high': bar.high.as_double(),
                    'low': bar.low.as_double(),
                    'identifier': identifier,
                },
                at=unix_nanos_to_dt(bar.ts_event)
            )
        except IngressError as e:
            self.logger.error(f"IngressError cannot write to questdb: {e}")
            raise Exception(f"ingress_bar cannot write to questdb: {e}")
