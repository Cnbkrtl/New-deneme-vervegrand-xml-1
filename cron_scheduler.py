import os
import redis
from rq import Queue
# Ana sync dosyasından SADECE cron için olan wrapper fonksiyonunu import et
from shopify_sync import run_sync_for_cron 
from config_manager import load_all_keys # Ayarları güvenli dosyadan okumak için
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def trigger_auto_sync():
    """Otomatik sync işlemini Redis Queue'ya görev olarak ekler."""
    try:
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            logger.error("REDIS_URL ortam değişkeni bulunamadı!")
            return
            
        r = redis.from_url(redis_url)
        q = Queue('default', connection=r)
        
        # Streamlit arayüzünden kaydedilmiş, şifreli ayarları yükle
        # NOT: Bu yapı, sistemde kayıtlı ilk kullanıcının ayarlarını kullanır.
        # Eğer birden fazla kullanıcı hesabı yönetiyorsanız, cron'un hangi 
        # kullanıcı için çalışacağını burada belirlemeniz gerekebilir.
        all_creds = load_all_keys()
        if not all_creds:
            logger.error("Otomatik sync için config dosyasında kayıtlı ayar bulunamadı.")
            return

        # Yapılandırma dosyasındaki ilk kullanıcı ayarlarını al
        # Kullanıcı adı önemli değil, sadece ilk ayar setini alıyoruz.
        first_user_key = next(iter(all_creds))
        creds = all_creds[first_user_key]

        # Gerekli parametreleri bir sözlük (dictionary) olarak hazırla
        task_kwargs = {
            "store_url": creds.get('shopify_store'),
            "access_token": creds.get('shopify_token'),
            "sentos_api_url": creds.get('sentos_api_url'),
            "sentos_api_key": creds.get('sentos_api_key'),
            "sentos_api_secret": creds.get('sentos_api_secret'),
            "sentos_cookie": creds.get('sentos_cookie')
        }

        # Eğer herhangi bir ayar eksikse, görevi başlatma ve hata ver
        if not all(task_kwargs.values()):
            logger.error(f"Otomatik sync için '{first_user_key}' kullanıcısının ayarları eksik. Lütfen kontrol edin.")
            return
            
        # Doğru fonksiyonu (`run_sync_for_cron`) doğru parametrelerle kuyruğa ekle
        job = q.enqueue(
            run_sync_for_cron,
            kwargs=task_kwargs, # Parametreleri keyword olarak gönder
            job_timeout='2h'   # Görev en fazla 2 saat sürebilir
        )
        
        logger.info(f"Otomatik senkronizasyon görevi başarıyla kuyruğa eklendi. Job ID: {job.id}")
                
    except Exception as e:
        logger.error(f"Otomatik sync tetiklenirken hata oluştu: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Otomatik sync tetikleyicisi çalıştırılıyor...")
    trigger_auto_sync()
    logger.info("Otomatik sync tetikleyicisi tamamlandı.")