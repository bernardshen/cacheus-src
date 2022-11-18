import hashlib
from .lib.pollutionator import Pollutionator
from .lib.visualizinator import Visualizinator
from .lib.dequedict import DequeDict
from .lib.cacheop import CacheOp
from .lib.priority import PrioEntry, get_priority, update_entry
from .lib.optional_args import process_kwargs
from randomdict import RandomDict
import numpy as np
import time


class ParaAdaSample:
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
        self.num_clients = 2
        self.merge_thresh = 0.1
        self.reward_type = "olecar"
        self.history_type = "global"
        
        print(self.experts, kwargs)
        process_kwargs(self, kwargs, ['experts', 'num_samples', 'num_clients', 
                       'merge_thresh', 'reward_type', 'history_type'])

        self.cache = RandomDict()
        self.prioInsts = [[get_priority(i)() for i in self.experts] for _ in range(self.num_clients)]

        self.history_size = cache_size // self.num_clients if self.history_type == 'local' else cache_size // 8
        self.hist = [DequeDict() for _ in range(self.num_clients)]
        self.ghist = DequeDict()

        self.initial_weight = 1 / len(self.experts)
        self.learning_rate = 0.45
        self.discount_rate = 0.005 ** (1 / self.cache_size)
        self.merge_thresh /= self.num_clients
        self.W = np.array([self.initial_weight for _ in self.experts], 
                          dtype=np.float32)
        self.client_old_W = [self.W.copy() for _ in range(self.num_clients)]
        self.client_new_W = [self.W.copy() for _ in range(self.num_clients)]
        self.client_acc_cnt = [0 for _ in range(self.num_clients)]
        self.cleint_miss_cnt = [0 for _ in range(self.num_clients)]
        self.client_panelty_cnt = [0 for _ in range(self.num_clients)]
        self.client_merge_cnt = [0 for _ in range(self.num_clients)]
        self.client_time = [0 for _ in range(self.num_clients)]
        self.client_reward_hist = [[] for _ in range(self.num_clients)]

        process_kwargs(self, kwargs, acceptable_kws=['learning_rate', 'merge_thresh'])

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
        x = ParaAdaSample.AdaSample_Entry(oblock, time.time(), freq)
        self.cache[oblock] = x
    
    def addToHistory(self, x, cid):
        hist = self.hist[cid] if self.history_type == 'local' else self.ghist
        if len(hist) == self.history_size:
            evicted = self.getLRU(hist)
            del hist[evicted.oblock]
        hist[x.oblock] = x

    def hit(self, oblock, cid):
        x = self.cache[oblock]
        for prio in self.prioInsts[cid]:
            prio.updateEntrySpecific(x)
        update_entry(x)

    def getEvictCandicates(self, cid):
        sampledKeys = [self.cache.random_key() for _ in range(self.num_samples)]
        candidates = []
        for prio in self.prioInsts[cid]:
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

    def getChoice(self, candidates: list, cid):
        candidateW = {}
        for i in range(len(candidates)):
            if candidates[i] not in candidateW:
                candidateW[candidates[i]] = 0
            candidateW[candidates[i]] += self.client_new_W[cid][i]
        rand = np.random.rand()
        s = 0
        candidateList = []
        for k, w in candidateW.items():
            s += w * (1 - self.learning_rate) + \
                 (self.learning_rate / len(candidateW))
            if rand <= s:
                return k
            candidateList.append(k)
        return candidateList[-1]

    def evict(self, cid):
        candidates = self.getEvictCandicates(cid)
        victim = self.getChoice(candidates, cid)
        
        victimEnt = self.cache.pop(victim)
        assert(victimEnt.oblock == victim)
        victimEnt.experts = []
        for i in range(len(candidates)):
            if victim == candidates[i]:
                victimEnt.experts.append(i)
        victimEnt.evicted_time = self.client_time[cid] if self.history_type == 'local' else self.time
        self.pollution.remove(victimEnt.oblock)
        self.addToHistory(victimEnt, cid)
        for inst in self.prioInsts[cid]:
            inst.evictCallback(victimEnt)
        return victimEnt.oblock

    def adjustWeights(self, rewards, cid):
        self.client_reward_hist[cid].append(rewards)
        reward = np.array(rewards, dtype=np.float32)
        self.client_new_W[cid] = self.client_new_W[cid] * np.exp(self.learning_rate * reward)
        for i in range(len(self.experts)):
            if self.client_new_W[cid][i] > 0.99:
                self.client_new_W[cid][i] = 0.99
            elif self.client_new_W[cid][i] < 0.01:
                self.client_new_W[cid][i] = 0.01
        self.client_new_W[cid] = self.client_new_W[cid] / np.sum(self.client_new_W[cid])

        # Occationally sync global
        if np.random.rand() < 0.2:
            self.client_old_W[cid] = self.W
        err = np.sum(np.abs(self.client_new_W[cid] - self.client_old_W[cid]))
        if err > self.merge_thresh or np.random.rand() < 0.1:
            for r in self.client_reward_hist[cid]:
                r = np.array(r, dtype=np.float32)
                self.W = self.W * np.exp(self.learning_rate * r)
            for i in range(len(self.experts)):
                self.W[i] = 0.99 if self.W[i] > 0.99 else self.W[i]
                self.W[i] = 0.01 if self.W[i] < 0.01 else self.W[i]
            self.W = self.W / np.sum(self.W)
            self.client_old_W[cid] = self.W
            self.client_new_W[cid] = self.W
            self.client_merge_cnt[cid] += 1
            self.client_reward_hist[cid] = []
        
    def getReward(self, entry: AdaSample_Entry, cid):
        pTime = self.client_time[cid] if self.history_type == 'local' else self.time
        if self.reward_type == "olecar":
            return -self.discount_rate / (pTime - entry.evicted_time)
        elif self.reward_type == "lecar":
            return -self.discount_rate ** (pTime - entry.evicted_time)
        assert(0)
        return 0

    def miss(self, oblock, cid):
        evicted = None
        freq = 1

        hist = self.hist[cid] if self.history_type == 'local' else self.ghist
        self.cleint_miss_cnt[cid] += 1

        if oblock in hist:
            self.client_panelty_cnt[cid] += 1
            entry = hist[oblock]
            freq = entry.freq + 1
            rewards = [0] * len(self.experts)
            for i in range(len(self.experts)):
                if i not in entry.experts:
                    continue
                rewards[i] = self.getReward(entry, cid)
            self.adjustWeights(rewards, cid)
            # del hist[oblock]
        
        if len(self.cache) == self.cache_size:
            evicted = self.evict(cid)
        
        self.addToCache(oblock, freq)
        
        return evicted
    
    def show_stats(self):
        merge = 0
        acc = 0
        misses = 0
        panelties = 0
        for i in range(self.num_clients):
            merge += self.client_merge_cnt[i]
            acc += self.client_acc_cnt[i]
            misses += self.cleint_miss_cnt[i]
            panelties += self.client_panelty_cnt[i]
        print(merge, acc, misses, panelties, merge/(acc+1), merge/(misses+1), merge/(panelties+1))


    def get_WHist(self):
        return self.WHist

    def request(self, oblock, ts):
        miss = True
        evicted = None
        cid = -1
        if type(oblock) == int:
            cid = int(hashlib.sha1(oblock.to_bytes(8, 'little')).hexdigest(), 16) % self.num_clients
        elif type(oblock) == str:
            cid = int(hashlib.sha1(oblock.encode('utf-8')).hexdigest(), 16) % self.num_clients
        assert(cid >= 0)

        self.client_acc_cnt[cid] += 1
        self.client_time[cid] += 1

        self.time += 1

        if oblock in self:
            miss = False
            self.hit(oblock, cid)
        else:
            evicted = self.miss(oblock, cid)

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