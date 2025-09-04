import os
import redis
import json
import logging
from datetime import datetime, timedelta
from rq import Queue
import shopify_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_scheduled_jobs_from_redis():
    """Redis'ten zamanlanmış job'ları al"""
    try:
        redis_url = os.getenv('REDIS_URL')
        r = redis.from_url(redis_url)
        
        # Scheduled jobs listesi
        jobs_json = r.get('scheduled_sync_jobs')
        if jobs_json:
            return json.loads(jobs_json)
        return []
    except Exception as e:
        logger.error(f"Scheduled jobs alınamadı: {e}")
        return []

def check_and_execute_jobs():
    """Zamanı gelen job'ları kontrol et ve çalıştır"""
    try:
        scheduled_jobs = get_scheduled_jobs_from_redis()
        current_time = datetime.now()
        
        redis_url = os.getenv('REDIS_URL')
        r = redis.from_url(redis_url)
        q = Queue('default', connection=r)
        
        updated_jobs = []
        
        for job_config in scheduled_jobs:
            if not job_config.get('enabled', True):
                updated_jobs.append(job_config)
                continue
                
            # Son çalışma zamanını kontrol et
            last_run_str = job_config.get('last_run')
            interval_minutes = job_config.get('interval_minutes', 120)
            
            should_run = False
            
            if not last_run_str:
                should_run = True
            else:
                try:
                    last_run = datetime.fromisoformat(last_run_str)
                    time_since_last = current_time - last_run
                    if time_since_last.total_seconds() >= (interval_minutes * 60):
                        should_run = True
                except:
                    should_run = True
            
            if should_run:
                logger.info(f"Zamanlanmış sync çalıştırılıyor: {job_config['name']}")
                
                # Job'ı kuyruğa ekle
                job = q.enqueue(
                    shopify_sync.sync_products_from_sentos_api,
                    job_config['shopify_store'],
                    job_config['shopify_token'], 
                    job_config['sentos_api_url'],
                    job_config['sentos_user_id'],
                    job_config['sentos_api_key'],
                    job_config.get('sentos_cookie', ''),
                    True,  # enable_detailed_logs
                    int(os.getenv('SYNC_MAX_WORKERS', '2')),
                    job_config['sync_mode'],
                    job_timeout='15m'
                )
                
                # Son çalışma zamanını güncelle
                job_config['last_run'] = current_time.isoformat()
                job_config['last_job_id'] = job.id
                
                logger.info(f"Job başlatıldı: {job.id}")
            
            updated_jobs.append(job_config)
        
        # Güncellenmiş job listesini Redis'e kaydet
        r.set('scheduled_sync_jobs', json.dumps(updated_jobs))
        
    except Exception as e:
        logger.error(f"Scheduler hatası: {e}")

if __name__ == "__main__":
    logger.info("Dynamic scheduler çalışıyor...")
    check_and_execute_jobs()
    logger.info("Dynamic scheduler tamamlandı.")
