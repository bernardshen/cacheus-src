from run import getReuseCount, getUniqueCount
from run import generateTraceNames, generateAlgorithmTests

import math
from multiprocessing import Process
from progressbar import ProgressBar

PARA_DIR="para"

def run_worker(config: dict):
    if 'request_count_type' in config:
        if config['request_count_type'] == 'reuse':
            requestCounter = getReuseCount
        elif config['request_count_type'] == 'unique':
            requestCounter = getUniqueCount
        else:
            raise ValueError("Unknown request_count_type found in config")
    else:
        requestCounter = getUniqueCount

    for trace in config['traces']:
        for trace_name in generateTraceNames(trace):
            print(trace_name)
            if any(map(lambda x: isinstance(x, float), config['cache_sizes'])):
                count, total = requestCounter(trace_name, config)
                window_size = int(0.01*total)
            else:
                window_size = 100
            for cache_size in config['cache_sizes']:
                cache_size_label = cache_size
                cache_size_label_type = 'size'
                if isinstance(cache_size, float):
                    cache_size = math.floor(cache_size * count)
                    cache_size_label_type = config['request_count_type']
                if cache_size < 3:
                    print(
                        "Cache size {} too small for trace {}. Calculated size is {}. Skipping"
                        .format(cache_size_label, trace_name, cache_size),
                        file=sys.stderr)
                    continue

                for algorithm in config['algorithms']:
                    for test in generateAlgorithmTests(algorithm, cache_size,
                                                       cache_size_label,
                                                       cache_size_label_type,
                                                       window_size, trace_name, config):
                        test.run(config)

def gather_results(pid, num_threads, out_fname):
    lines = []
    for i in range(num_threads):
        fname = os.path.join(PARA_DIR, "{}-{}.csv".format(pid, i))
        with open(fname, 'r') as f:
            lines += f.readlines()
        os.remove(fname)
    with open(out_fname, 'w') as f:
        f.writelines(lines)

if __name__ == '__main__':
    import sys
    import os
    import json

    if not os.path.exists(PARA_DIR):
        os.mkdir(PARA_DIR)

    if len(sys.argv) != 3:
        print("Usage: python run_para.py <config> <num_threads>")

    with open(sys.argv[1], 'r') as f:
        config = json.loads(f.read())
    if 'twitter-all' in config['traces']:
        config['traces'] += ["../traces/twitter/cluster{:03d}.twitter".format(i)
            for i in range(1, 55)]
        config['traces'].remove('twitter-all')
    if 'webmail-all' in config['traces']:
        config['traces'] += ["../traces/webmail/webmail.cs.fiu.edu-110108-113008.{}.blkparse".format(i)
            for i in range(1, 21)]
        config['traces'].remove('webmail-all')
    for i, wl in enumerate(config['traces']):
        if 'twitter' == wl[: 8]:
            twitter_id = wl.split('-')[1]
            config['traces'][i] = "../traces/twitter/cluster{}.twitter".format(twitter_id)
    
    num_threads = int(sys.argv[2])

    # generate sub configs
    config_list = [config.copy() for _ in range(num_threads)]
    for i in range(num_threads):
        config_list[i]['traces'] = []
    # assign workload   
    for i, wl in enumerate(config['traces']):
        tid = i % num_threads
        config_list[tid]['traces'].append(wl)

    process_list = []
    pid = os.getpid()
    for i in range(num_threads):
        config_list[i]['output_csv'] = 'para/{}-{}.csv'.format(pid, i)
        p = Process(target=run_worker, args=(config_list[i], ))
        p.start()
        process_list.append(p)
    
    print("All process start")
    progress = ProgressBar()
    for p in progress(process_list):
        p.join()
    gather_results(pid, num_threads, config['output_csv'])