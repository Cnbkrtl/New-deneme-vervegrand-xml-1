import os
import redis
from rq import Queue
import shopify_sync # GÜNCELLEME: Direkt modülü import ediyoruz
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def trigger_auto_sync():
    """Otomatik sync işlemini RQ kuyruğuna ekler."""
    try:
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            logger.error("REDIS_URL ortam değişkeni bulunamadı.")
            return
            
        r = redis.from_url(redis_url)
        q = Queue('default', connection=r)
        
        # Gerekli tüm ortam değişkenlerini kontrol et
        required_vars = [
            'AUTO_SYNC_SHOPIFY_STORE', 'AUTO_SYNC_SHOPIFY_TOKEN', 
            'AUTO_SYNC_SENTOS_API_URL', 'AUTO_SYNC_SENTOS_API_KEY', 
            'AUTO_SYNC_SENTOS_API_SECRET' # GÜNCELLEME: API Secret eklendi
        ]
        
        config = {var: os.getenv(var) for var in required_vars}
        
        if not all(config.values()):
            missing = [key for key, val in config.items() if not val]
            logger.error(f"Otomatik senkronizasyon kimlik bilgileri eksik: {', '.join(missing)}")
            return
        
        # GÜNCELLEME: Artık 'run_sync_for_cron' fonksiyonu çağrılıyor
        job = q.enqueue(
            shopify_sync.run_sync_for_cron,
            kwargs={
                "store_url": config['AUTO_SYNC_SHOPIFY_STORE'],
                "access_token": config['AUTO_SYNC_SHOPIFY_TOKEN'],
                "sentos_api_url": config['AUTO_SYNC_SENTOS_API_URL'],
                "sentos_api_key": config['AUTO_SYNC_SENTOS_API_KEY'],
                "sentos_api_secret": config['AUTO_SYNC_SENTOS_API_SECRET'],
                "sentos_cookie": os.getenv('AUTO_SYNC_SENTOS_COOKIE', ''),
                "sync_mode": "Stock & Variants Only", # Cron için varsayılan mod
                "max_workers": 2
            },
            job_timeout='20m'
        )
        
        logger.info(f"Otomatik senkronizasyon görevi kuyruğa eklendi: {job.id}")
        
    except Exception as e:
        logger.error(f"Otomatik senkronizasyon tetiklenirken hata oluştu: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info(f"Otomatik senkronizasyon tetikleyicisi çalışıyor ({datetime.now()})")
    trigger_auto_sync()
    logger.info("Otomatik senkronizasyon tetikleyicisi tamamlandı.")