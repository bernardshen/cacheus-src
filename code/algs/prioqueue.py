from .lib.pollutionator import Pollutionator
from .lib.visualizinator import Visualizinator
from .lib.cacheop import CacheOp
from .lib.priority import PrioEntry, Priority, get_priority, update_entry
from .lib.heapdict import HeapDict
from .lib.optional_args import process_kwargs
from randomdict import RandomDict
import time

class PrioQueue:
    class PQEntry(PrioEntry):
        def __init__(self, oblock, ts, freq) -> None:
            super().__init__(oblock, ts, freq)
            self.priority = 0
        
        def __lt__(self, other):
            if self.priority == other.priority:
                return self.acc_ts < other.acc_ts
            return self.priority < other.priority

    def __init__(self, cache_size, window_size, **kwargs):
        self.cache_size = cache_size
        self.priority = 'lru'
        
        process_kwargs(self, kwargs, ['priority'])

        self.cache = HeapDict()
        self.prioInst = get_priority(self.priority)()

        self.visual = Visualizinator(labels=['hit-rate'],
                                     windowed_labels=['hit-rate'],
                                     window_size=window_size,
                                     **kwargs)

        self.pollution = Pollutionator(cache_size, **kwargs)
        self.time = 0

    def __contains__(self, oblock):
        return oblock in self.cache

    def cacheFull(self):
        return len(self.cache) == self.cache_size

    def addToCache(self, oblock: PQEntry):
        x = self.PQEntry(oblock, time.time(), 1)
        x.priority = self.prioInst.getPriority(x)
        self.cache[oblock] = x

    def hit(self, oblock: PQEntry):
        x = self.cache[oblock]
        self.prioInst.updateEntrySpecific(x)
        update_entry(x)
        x.priority = self.prioInst.getPriority(x)
        self.cache[oblock] = x

    def evict(self):
        entry = self.cache.popMin()
        self.pollution.remove(entry.oblock)
        return entry.oblock

    def miss(self, oblock):
        evicted = None

        if len(self.cache) == self.cache_size:
            evicted = self.evict()
        self.addToCache(oblock)

        return evicted

    def request(self, oblock, ts):
        miss = True
        evicted = None

        self.time += 1

        if oblock in self:
            miss = False
            self.hit(oblock)
        else:
            evicted = self.miss(oblock)

        self.visual.addWindow({'hit-rate': 0 if miss else 1}, self.time, ts)

        # Pollutionator
        if miss:
            self.pollution.incrementUniqueCount()
        self.pollution.setUnique(oblock)
        self.pollution.update(self.time)

        op = CacheOp.INSERT if miss else CacheOp.HIT

        return op, evicted
