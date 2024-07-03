import bluesky
from bluesky import plans as bsp
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.status import Status
from bluesky.utils import ProgressBarManager
import time

class Settable(object):
    def __init__(self, name: str):
        self.name = name
        self.parent = None
        self.value = 0.0

    def describe(self) -> dict:
        out = dict()
        out[f"{self.name}_setpoint"] = {"source": "FakeSettable", "dtype": "number", "shape": []}
        out[f"{self.name}_readback"] = {"source": "FakeSettable", "dtype": "number", "shape": []}
        return out

    def read(self) -> dict:
        ts = time.time()
        out = dict()
        out[f"{self.name}_setpoint"] = {"value": self.value, "timestamp": ts}
        out[f"{self.name}_readback"] = {"value": self.value, "timestamp": ts}
        return out

    def set(self, value) -> Status:
        self.value = value
        s = Status()
        s.set_finished()
        return s

    @property
    def position(self):
        return self.value


w1 = Settable("w1")
voltage = Settable("voltage")


class MyProcessor(object):

    def __init__(self):
        pass

    def __call__(self, name, document):
        print(f"Name: {name}, Document: {document}")


RE = bluesky.RunEngine()

mp = MyProcessor()
# RE.subscribe(mp)
bec = BestEffortCallback()
RE.subscribe(bec)
# RE.waiting_hook = ProgressBarManager()

# RE(bsp.scan([voltage], w1, -1, 1, 50))

RE(bluesky.plans.count([w1, voltage], num=5, delay=1))