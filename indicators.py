import overrides
import pandas as pd
import numpy as np
from nautilus_trader.indicators.base.indicator import Indicator
from nautilus_trader.indicators.average.ema import ExponentialMovingAverage
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.core.datetime import unix_nanos_to_dt, maybe_unix_nanos_to_dt
from overrides.overrides import override


class TrackerMulti(Indicator):
    def __init__(self, sub_indicator: Indicator, value_getters: dict[str, callable], styling: dict):
        super().__init__([])
        self.sub_indicator = sub_indicator
        self.value_getters = value_getters

        self.values: dict[str, list] = {}

        for name in value_getters.keys():
            self.values[name] = []
        self.timestamps = []

        self.styling: dict = styling

    def __repr__(self):
        return f"TrackerMulti({self.sub_indicator}, {self.value_getters})"
    def get_df(self) -> pd.DataFrame:
        df = pd.DataFrame(data={
            'ts': [maybe_unix_nanos_to_dt(ts) for ts in self.timestamps],
        })
        for name, values in self.values.items():
            df[name] = values

        df['ts'] = pd.to_datetime(df['ts'])
        
        df.set_index('ts', inplace=True, drop=True)
        return df

    def handle_bar(self, Bar_bar):
        self.sub_indicator.handle_bar(Bar_bar)
        if self.sub_indicator.initialized:
            self._update_raw(Bar_bar)

    def _update_raw(self, bar: Bar):
        for name, getter in self.value_getters.items():
            self.values[name].append(getter(self.sub_indicator))
        self.timestamps.append(bar.ts_event)



    @property
    def initialized(self):
        return self.sub_indicator.initialized

    @property
    def has_inputs(self):
        return self.sub_indicator.has_inputs


class TrackerFloat(Indicator):
    def __init__(self, sub_indicator: Indicator, value_getter: callable):
        super().__init__([])
        self.sub_indicator = sub_indicator
        self.values = []
        self.timestamps = []
        self.value_getter = value_getter

    @property
    def initialized(self):
        return self.sub_indicator.initialized

    @property
    def has_inputs(self):
        return self.sub_indicator.has_inputs


    @override
    def reset(self):
        self.sub_indicator.reset()
        self.values = []
        self.timestamps = []
    @property
    def latest(self):
        return self.values[-1]

    @override
    def handle_bar(self, bar: Bar):
        self.sub_indicator.handle_bar(bar)
        if self.sub_indicator.initialized:
            self._update_raw(bar, self.value_getter())

    def _update_raw(self, bar: Bar, value: float):
        self.values.append(value)
        self.timestamps.append(bar.ts_event)

