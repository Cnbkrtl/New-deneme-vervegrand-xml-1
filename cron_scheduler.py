import os
import requests
import redis
from rq import Queue
import shopify_sync
from datetime import datetime
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def trigger_auto_sync():
    """Otomatik sync işlemini tetikle"""
    try:
        # Redis bağlantısı
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            logger.error("REDIS_URL environment variable not found")
            return
            
        r = redis.from_url(redis_url)
        q = Queue('default', connection=r)
        
        # Auto sync parametreleri (environment variables'dan al)
        shopify_store = os.getenv('AUTO_SYNC_SHOPIFY_STORE')
        shopify_token = os.getenv('AUTO_SYNC_SHOPIFY_TOKEN')
        sentos_api_url = os.getenv('AUTO_SYNC_SENTOS_API_URL')
        sentos_user_id = os.getenv('AUTO_SYNC_SENTOS_USER_ID')
        sentos_api_key = os.getenv('AUTO_SYNC_SENTOS_API_KEY')
        sentos_cookie = os.getenv('AUTO_SYNC_SENTOS_COOKIE')
        
        if not all([shopify_store, shopify_token, sentos_api_url, sentos_user_id, sentos_api_key]):
            logger.error("Auto sync credentials not configured in environment variables")
            return
            
        # Optimized parameters - daha küçük değerler
        batch_size = int(os.getenv('SYNC_BATCH_SIZE', '5'))
        max_workers = int(os.getenv('SYNC_MAX_WORKERS', '2'))
        
        # Job oluştur - daha kısa timeout ile
        job = q.enqueue(
            shopify_sync.sync_products_from_sentos_api,
            shopify_store,
            shopify_token,
            sentos_api_url,
            sentos_user_id,
            sentos_api_key,
            sentos_cookie or "",
            True,  # enable_detailed_logs
            max_workers,    # optimize edilmiş worker sayısı
            "Stock & Variants Only",  # sync_mode
            job_timeout='12m'  # 20'den 12 dakikaya düşürüldü
        )
        
        # Global state'i Redis'e kaydet
        import json
        state_data = {
            'sync_status': 'running',
            'sync_job_id': job.id,
            'sync_start_time': datetime.now().isoformat(),
            'sync_type': 'auto_cron',
            'last_update': datetime.now().isoformat()
        }
        r.setex('global_sync_state', 3600, json.dumps(state_data))
        
        logger.info(f"Auto sync job queued: {job.id} (timeout: 12m, workers: {max_workers}, batch: {batch_size})")
        
        # Keep-alive ping
        app_url = os.getenv('APP_URL')
        if app_url:
            try:
                requests.get(f"{app_url}/_stcore/health", timeout=10)
                logger.info("Keep-alive ping sent successfully")
            except Exception as e:
                logger.warning(f"Keep-alive ping failed: {e}")
                
    except Exception as e:
        logger.error(f"Auto sync failed: {e}")

if __name__ == "__main__":
    logger.info(f"Starting auto sync at {datetime.now()}")
    trigger_auto_sync()
    logger.info("Auto sync trigger completed")
