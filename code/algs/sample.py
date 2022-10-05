from .lib.pollutionator import Pollutionator
from .lib.visualizinator import Visualizinator
from .lib.cacheop import CacheOp
from .lib.priority import PrioEntry, get_priority, update_entry
from .lib.optional_args import process_kwargs
from randomdict import RandomDict
import time


class Sample:
    def __init__(self, cache_size, window_size, **kwargs):
        self.cache_size = cache_size
        self.priority = 'lru'
        self.num_samples = 5
        
        print(self.priority, kwargs)
        process_kwargs(self, kwargs, ['priority', 'num_samples'])

        self.cache = RandomDict()
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

    def addToCache(self, oblock):
        x = PrioEntry(oblock, time.time(), 1)
        self.cache[oblock] = x

    def hit(self, oblock):
        x = self.cache[oblock]
        self.prioInst.updateEntrySpecific(x)
        update_entry(x)

    def evict(self):
        sampledKeys = [self.cache.random_key() for _ in range(self.num_samples)]
        min_key = sampledKeys[0]
        min_prio = self.prioInst.getPriority(self.cache[min_key])
        for k in sampledKeys:
            cur_entry = self.cache[k]
            cur_prio  = self.prioInst.getPriority(cur_entry)
            if cur_prio < min_prio:
                min_key = k
                min_prio = cur_prio
        entry = self.cache.pop(min_key)
        self.pollution.remove(entry.oblock)
        self.prioInst.evictCallback(entry)
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
