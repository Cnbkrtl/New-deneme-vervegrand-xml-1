# worker.py

import os
import sys
from redis import Redis
from rq import Queue
from rq.worker import SimpleWorker

project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

listen = ['default']
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = Redis.from_url(redis_url)

if __name__ == '__main__':
    print("Worker BASİT MODDA başlatılıyor... Kuyruklar dinleniyor:", listen)
    queues = [Queue(name, connection=conn) for name in listen]
    worker = SimpleWorker(queues, connection=conn)
    worker.work(burst=False)