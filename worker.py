# worker.py (GÜNCELLENMİŞ HALİ)

import os
import sys
from redis import Redis
# 'Connection' import'u kaldırıldı, artık gerekli değil.
from rq import Worker, Queue

# Bu satırlar, worker'ın ana proje modüllerini (örn: shopify_sync) bulabilmesi için gereklidir.
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

# Hangi kuyrukları dinleyeceğini belirtiyoruz.
listen = ['default']

# Redis bağlantı adresi
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Redis'e bağlanıyoruz.
conn = Redis.from_url(redis_url)

if __name__ == '__main__':
    print("Worker başlatılıyor... Kuyruklar dinleniyor:", listen)
    
    # 'with Connection(conn):' bloğu kaldırıldı.
    # Worker'a dinleyeceği kuyrukları ve bağlantıyı doğrudan parametre olarak veriyoruz.
    queues = [Queue(name, connection=conn) for name in listen]
    worker = Worker(queues, connection=conn)
    
    # worker.work() komutu işçiyi başlatır. 
    # Sürekli çalışması ve yeni görevleri beklemesi için bu şekilde bırakıyoruz.
    worker.work()