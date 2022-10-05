from abc import ABCMeta, abstractmethod
import time

class PrioEntry:
    def __init__(self, oblock, ts, freq) -> None:
        self.oblock = oblock
        self.insert_ts = ts
        self.acc_ts  = ts
        self.lruk_ts = ts
        self.freq = freq
        self.lrfu_counter  = freq
        self.lfuda_counter = freq

    def __repr__(self) -> str:
        return "(o={}, ts={}, freq={})".format(
            self.oblock, self.ts, self.freq)
    
class Priority(object, metaclass=ABCMeta):
    def __init__(self) -> None:
        pass

    def updateEntrySpecific(self, entry: PrioEntry):
        pass
    
    @abstractmethod
    def getPriority(self, entry: PrioEntry):
        pass

    def evictCallback(self, entry: PrioEntry):
        pass
    
class LRUPriority(Priority):
    def getPriority(self, entry: PrioEntry):
        return entry.acc_ts

class LFUPriority(Priority):
    def getPriority(self, entry: PrioEntry):
        return entry.freq
    
class LRFUPriority(Priority):
    lam = 0.5
    def f(self, delta):
        return 0.5 ** (LRFUPriority.lam * delta)

    def updateEntrySpecific(self, entry: PrioEntry):
        current_ts = time.time()
        entry.lrfu_counter = int(1 + self.f(current_ts - entry.acc_ts) \
                                 * entry.freq)
    
    def getPriority(self, entry: PrioEntry):
        return entry.lrfu_counter

class HyperbolicPriority(Priority):
    def getPriority(self, entry: PrioEntry):
        dur = time.time() - entry.acc_ts
        dur = 1e-6 if dur < 1e-6 else dur
        return entry.freq / (dur)

class LRUKPriority(Priority):
    K_ = 4
    def updateEntrySpecific(self, entry: PrioEntry):
        if entry.freq % LRUKPriority.K_ == 0:
            entry.lruk_ts = time.time()
    
    def getPriority(self, entry: PrioEntry):
        return entry.lruk_ts

class FIFOPriority(Priority):
    def getPriority(self, entry: PrioEntry):
        return entry.insert_ts
    
class LFUDAPriority(Priority):
    def __init__(self) -> None:
        super().__init__()
        self.L = 1
    
    def updateEntrySpecific(self, entry: PrioEntry):
        entry.lfuda_counter += self.L
    
    def getPriority(self, entry: PrioEntry):
        return entry.lfuda_counter
    
    def evictCallback(self, entry: PrioEntry):
        self.L = entry.lfuda_counter


def get_priority(prio_name: str):
    prio_name = prio_name.lower()
    print(prio_name)

    if prio_name == 'lru':
        return LRUPriority
    if prio_name == 'lfu':
        return LFUPriority
    if prio_name == 'lrfu':
        return LRFUPriority
    if prio_name == 'lruk':
        return LRUKPriority
    if prio_name == 'hyperbolic':
        return HyperbolicPriority
    if prio_name == 'fifo':
        return FIFOPriority
    if prio_name == 'lfuda':
        return LFUDAPriority
    return None

def update_entry(entry: PrioEntry):
    entry.acc_ts = time.time()
    entry.freq  += 1