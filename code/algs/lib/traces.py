from .optional_args import process_kwargs
import random


# Basic Trace Reader as Base Class
class Trace:
    def __init__(self, file, count=False, alg_args=None, **kwargs):
        # Duration (in Hours)
        self.duration = 0
        self.para_clients = 1

        process_kwargs(self, kwargs, acceptable_kws=['duration'])

        if count == False and 'para_clients' in alg_args:
            self.para_clients = alg_args['para_clients']

        # Setup
        self.file = file
        self.unique = set()
        self.reuse = set()
        self.requests = 0
        self.start_time = 0
        
        self.start_tick = 0
        self.next_tick = 0

        self.last_line = None

        # Progress (0-100%)
        self.progress = 0

        # get ending index of file for progress
        f = open(self.file, 'r')
        self.lines = f.readlines()
        self.client_lines = self.get_client_lines()
        self.client_lines_idx = [0] * self.para_clients
        self.end = len(self.lines)
        print("Num client: ", self.para_clients)
        f.close()
    
    def get_client_lines(self):
        clients = [[]] * self.para_clients
        for i, l in enumerate(self.lines):
            cid = i % self.para_clients
            clients[cid].append(l)
        return clients
    
    def get_line(self):
        unfinished_clients = []
        for cid, idx in enumerate(self.client_lines_idx):
            if idx < len(self.client_lines[cid]):
                unfinished_clients.append(cid)
        cid = random.randint(0, len(unfinished_clients) - 1)
        idx = self.client_lines_idx[cid]
        ret_line = self.client_lines[cid][idx]
        self.client_lines_idx[cid] += 1
        return ret_line

    def readLine(self, line):
        yield int(line), False, False

    def read(self):
        cnt = 0
        try:
            while True:
                line = self.get_line()
                if not line: break
                self.last_line = line
                self.progress = round(100 * (cnt / self.end))
                for lba, write, ts in self.readLine(line):
                    if lba == None: continue

                    self.requests += 1

                    if lba in self.unique:
                        self.reuse.add(lba)
                    self.unique.add(lba)

                    yield lba, write, ts
                cnt += 1
                if cnt == self.end:
                    break
        except EOFError:
            pass

    def num_requests(self):
        return self.requests

    def num_unique(self):
        return len(self.unique)

    def num_reuse(self):
        return len(self.reuse)


class TwitterNTrace(Trace):
    _ts         = 0
    _key        = 1
    _key_sz     = 2
    _val_sz     = 3
    _client_id  = 4
    _op         = 5
    _ttl        = 6
    def inDuration(self, time):
        return True
    
    def readLine(self, line):
        line = line.split(' ')
        ts  = line[TwitterNTrace._ts]
        key = line[TwitterNTrace._key]
        op  = line[TwitterNTrace._op]
        write = op not in ['get', 'gets']
        yield key, write, ts

class TwitterTrace(Trace):
    _ts         = 0
    _key        = 1
    _key_sz     = 2
    _val_sz     = 3
    _client_id  = 4
    _op         = 5
    _ttl        = 6
    def inDuration(self, time):
        return True
    
    def readLine(self, line):
        line = line.split(',')
        ts  = line[TwitterTrace._ts]
        key = line[TwitterTrace._key]
        op  = line[TwitterTrace._op]
        write = op not in ['get', 'gets']
        yield key, write, ts

class FIUTrace(Trace):
    def inDuration(self, time):
        if self.duration == 0:
            return True

        if self.start_time == 0:
            self.start_time = time
            self.end_time = time + (self.duration * 10**9 * 60 * 60)

        return time < self.end_time

    def tickHour(self, time):
        if self.start_tick == 0:
            self.start_tick = time
        self.next_tick += time - self.start_tick
        self.start_tick = time

        return int(self.next_tick/(3.6 * 10**12))

    def readLine(self, line):
        blocks_per_page = 8
        line = line.split(' ')

        ts = int(line[0])
        lba = int(line[3])
        size = int(line[4])
        write = line[5][0] == 'W'
        align = lba % blocks_per_page
        lba -= align
        size += align

        if not self.inDuration(ts):
            raise EOFError("End of duration")

        ts_hour = self.tickHour(ts)

        for offset in range(0, size, blocks_per_page):
            yield lba + offset, write, ts_hour


class MSRTrace(Trace):
    def inDuration(self, time):
        if self.duration == 0:
            return True

        if self.start_time == 0:
            self.start_time = time
            self.end_time = time + (self.duration * 10**7 * 60 * 60)

        return time < self.end_time

    def tickHour(self, time):
        if self.start_tick == 0:
            self.start_tick = time
        self.next_tick += time - self.start_tick
        self.start_tick = time

        return int(self.next_tick/(3.6 * 10**9))

    def readLine(self, line):
        blocksize = 512
        line = line.split(',')

        ts = int(line[0])
        write = line[3][0] == 'W'
        lba = int(line[4])
        size = int(line[5])
        align = lba % blocksize
        lba -= align
        size += align

        #if size % blocksize > 0:
        #    size += blocksize

        if not self.inDuration(ts):
            raise EOFError("End of duration")

        ts_hour = self.tickHour(ts)

        for offset in range(0, size, blocksize):
            yield lba + offset, write, ts_hour

class VisaTrace(Trace):
    def inDuration(self, time):
        if self.duration == 0:
            return True

        if self.start_time == 0:
            self.start_time = time
            self.end_time = time + (self.duration * 60 * 60)

        return time < self.end_time

    def tickHour(self, time):
        if self.start_tick == 0:
            self.start_tick = time
        self.next_tick += time - self.start_tick
        self.start_tick = time

        return int(self.next_tick/(3.6 * 10**3))

    def readLine(self, line):
        blocks_per_page = 8
        line = line.split(' ')
        ts = float(line[0])
        lba = int(line[4])
        size = int(line[5])
        write = line[6][0] == 'W'
        align = lba % blocks_per_page
        lba -= align
        size += align

        ts_hour = self.tickHour(ts)

        for offset in range(0, size, blocks_per_page):
            yield lba + offset, write, ts_hour


class NexusTrace(Trace):
    def readLine(self, line):
        blocks_per_page = 8
        line = line.split("\t\t")
        lba = int(line[0])
        size = int(line[1])
        write = int(line[3]) == 3 or int(line[3]) == 5

        for offset in range(0, size, blocks_per_page):
            yield lba + offset, write, None


class UMassTrace(Trace):
    def readLine(self, line):
        blocksize = 512
        line = line.split(',')
        lba = int(line[1])
        size = int(line[2])

        for offset in range(0, size, blocksize):
            yield lba + offset, False, None


class SynthTrace(Trace):
    def readLine(self, line):
        lba = int(line)
        if lba < 0:
            yield None, False, None
        else:
            yield lba, False, None

class CloudPhysics(Trace):
    def inDuration(self, time):
        if self.duration == 0:
            return True

        if self.start_time == 0:
            self.start_time = time
            self.end_time = time + (self.duration * 60 * 60)

        return time < self.end_time

    def tickHour(self, time):
        if self.start_tick == 0:
            self.start_tick = time
        self.next_tick += time - self.start_tick
        self.start_tick = time

        return int(self.next_tick/(3.6 * 10**3))

    def readLine(self, line):
        blocksize = 512
        line = line.split(' ')

        ts = float(line[1])
        write = line[0] == 'W'
        lba = int(line[2])
        size = int(line[3])

        if not self.inDuration(ts):
            raise EOFError("End of duration")

        ts_hour = self.tickHour(ts)

        for offset, _ in enumerate(range(0, size, blocksize)):
            yield lba + offset, write, ts_hour


def get_trace_reader(trace_type):
    trace_type = trace_type.lower()
    if trace_type == 'fiu':
        return FIUTrace
    if trace_type == 'msr':
        return MSRTrace
    if trace_type == 'visa':
        return VisaTrace
    if trace_type == 'nexus':
        return NexusTrace
    if trace_type == 'umass':
        return UMassTrace
    if trace_type == 'synth':
        return SynthTrace
    if trace_type == 'physics':
        return CloudPhysics
    if trace_type == 'twitter':
        return TwitterTrace
    if trace_type == 'twittern':
        return TwitterNTrace
    raise ValueError("Could not find trace reader for {}".format(trace_type))


def identify_trace(filename):
    if filename.endswith('.blkparse'):
        return 'fiu'
    if filename.endswith('.csv'):
        return 'msr'
    if filename.endswith('.blk'):
        return 'visa'
    if filename.endswith('.txt'):
        return 'nexus'
    if filename.endswith('.spc'):
        return 'umass'
    if filename.endswith('.trc') or filename.endswith('.tx'):
        return 'synth'
    if filename.endswith('.itrace'):
        return 'physics'
    if filename.endswith('.twitter'):
        return 'twitter'
    if filename.endswith('.twittern'):
        return 'twittern'
    raise ValueError("Could not identify trace type of {}".format(filename))


def read_trace_file(filename):
    trace_type = identify_trace(filename)
    trace_reader = get_trace_reader(trace_type)
    reader = trace_reader(filename)
    for lba, write, ts in reader.read():
        yield lba, write, ts


if __name__ == '__main__':
    import sys
    for lba, write, ts in read_trace_file(sys.argv[1]):
        print(lba, write, ts)
