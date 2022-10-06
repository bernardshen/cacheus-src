from .lib.pollutionator import Pollutionator
from .lib.visualizinator import Visualizinator
from .lib.dequedict import DequeDict
from .lib.cacheop import CacheOp
from .lib.priority import PrioEntry, get_priority, update_entry
from .lib.optional_args import process_kwargs
from randomdict import RandomDict
import numpy as np
import time


class AdaSample:
    class AdaSample_Entry(PrioEntry):
        def __init__(self, oblock, ts, freq) -> None:
            super().__init__(oblock, ts, freq)
            self.experts = []
            self.evicted_time = None
        
        def __repr__(self) -> str:
            return "(o={}, et={}, experts={})".format(
                self.oblock, self.evicted_time, self.experts)

    def __init__(self, cache_size, window_size, **kwargs):
        self.cache_size = cache_size
        self.experts = ['lru', 'lfu']
        self.num_samples = 5
        self.reward_type = 'olecar'
        
        print(self.experts, kwargs)
        process_kwargs(self, kwargs, ['experts', 'num_samples', 'reward_type'])

        self.cache = RandomDict()
        self.prioInsts = [get_priority(i)() for i in self.experts]

        self.history_size = cache_size
        self.hist = DequeDict()

        self.initial_weight = 1 / len(self.experts)
        self.learning_rate = 0.45
        self.discount_rate = 0.005 ** (1 / self.cache_size)
        self.W = np.array([self.initial_weight for _ in self.experts], 
                          dtype=np.float32)

        process_kwargs(self, kwargs, acceptable_kws=['learning_rate'])

        self.visual = Visualizinator(labels=['hit-rate'],
                                     windowed_labels=['hit-rate'],
                                     window_size=window_size,
                                     **kwargs)

        self.pollution = Pollutionator(cache_size, **kwargs)
        self.time = 0
        self.WHist = []

    def __contains__(self, oblock):
        return oblock in self.cache

    def cacheFull(self):
        return len(self.cache) == self.cache_size
    
    def getLRU(self, dequeDict):
        return dequeDict.first()

    def addToCache(self, oblock, freq):
        x = AdaSample.AdaSample_Entry(oblock, time.time(), freq)
        self.cache[oblock] = x
    
    def addToHistory(self, x):
        if len(self.hist) == self.history_size:
            evicted = self.getLRU(self.hist)
            del self.hist[evicted.oblock]
        self.hist[x.oblock] = x

    def hit(self, oblock):
        x = self.cache[oblock]
        for prio in self.prioInsts:
            prio.updateEntrySpecific(x)
        update_entry(x)

    def getEvictCandicates(self):
        sampledKeys = [self.cache.random_key() for _ in range(self.num_samples)]
        candidates = []
        for prio in self.prioInsts:
            min_key = sampledKeys[0]
            min_prio = prio.getPriority(self.cache[min_key])
            for k in sampledKeys:
                cur_entry = self.cache[k]
                cur_prio  = prio.getPriority(cur_entry)
                if cur_prio < min_prio:
                    min_key = k
                    min_prio = cur_prio
            candidates.append(min_key)
        return candidates

    def getChoice(self, candidates: list):
        candidateW = {}
        for i in range(len(candidates)):
            if candidates[i] not in candidateW:
                candidateW[candidates[i]] = 0
            candidateW[candidates[i]] += self.W[i]
        rand = np.random.rand()
        s = 0
        for k, w in candidateW.items():
            s += w * (1 - self.learning_rate) + \
                 (self.learning_rate / len(candidateW))
            if rand <= s:
                return k
        assert(0)
        return None

    def evict(self):
        candidates = self.getEvictCandicates()
        victim = self.getChoice(candidates)
        
        victimEnt = self.cache.pop(victim)
        assert(victimEnt.oblock == victim)
        victimEnt.experts = []
        for i in range(len(candidates)):
            if victim == candidates[i]:
                victimEnt.experts.append(i)
        victimEnt.evicted_time = self.time
        self.pollution.remove(victimEnt.oblock)
        self.addToHistory(victimEnt)
        for inst in self.prioInsts:
            inst.evictCallback(victimEnt)
        return victimEnt.oblock

    def adjustWeights(self, rewards):
        reward = np.array(rewards, dtype=np.float32)
        self.W = self.W * np.exp(self.learning_rate * reward)
        self.W = self.W / np.sum(self.W)
    
    def getReward(self, entry: AdaSample_Entry):
        if self.reward_type == 'olecar':
            return -self.discount_rate / (self.time - entry.evicted_time)
        elif self.reward_type == 'lecar':
            return -self.discount_rate ** (self.time - entry.evicted_time)
        assert(0)
        return 0

    def miss(self, oblock):
        evicted = None
        freq = 1

        if oblock in self.hist:
            entry = self.hist[oblock]
            freq = entry.freq + 1
            rewards = [0] * len(self.experts)
            for i in range(len(self.experts)):
                if i not in entry.experts:
                    continue
                rewards[i] = self.getReward(entry)
                # rewards[i] = -(self.discount_rate) / (self.time - entry.evicted_time)
            self.adjustWeights(rewards)
        
        if len(self.cache) == self.cache_size:
            evicted = self.evict()
        
        self.addToCache(oblock, freq)
        
        return evicted
    
    def get_WHist(self):
        return self.WHist

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

        if self.time % 50 == 0:
            self.WHist.append([float(i) for i in list(self.W)])

        return op, evicted
