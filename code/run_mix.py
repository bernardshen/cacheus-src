import json
import sys

lru_lfu_num = [[i, 10 - i] for i in range(0, 11, 1)]

if __name__ == '__main__':
    import subprocess

    if len(sys.argv) != 2:
        print("Usage: python run_mix.py <config>")
        exit(1)
    config = json.loads(open(sys.argv[1], 'r').read())
    for arg in lru_lfu_num:
        config['lru_lfu_num'] = arg
        json.dump(config, open(sys.argv[1], 'w'), indent=4)
        subprocess.run("python run.py {}".format(sys.argv[1]))
