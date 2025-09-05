import os
import logging
import sys
import threading
import re

# Proje yolunu Python path'ine ekle
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

# GÜNCELLEME: Ana senkronizasyon fonksiyonunu doğrudan içe aktarıyoruz.
from shopify_sync import sync_products_from_sentos_api

# Temel loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    Ortam değişkenlerinden (GitHub Secrets) ayarları okur ve
    zamanlanmış senkronizasyon görevini başlatır.
    """
    
    # Hangi modda çalışacağını ortam değişkeninden oku.
    sync_mode_to_run = os.getenv("SYNC_MODE", "Sadece Stok ve Varyantlar")

    logging.info(f"GitHub Actions tarafından tetiklenen senkronizasyon başlıyor... Mod: {sync_mode_to_run}")

    # Gerekli ayarları GitHub Secrets'tan oku
    config = {
        "store_url": os.getenv("SHOPIFY_STORE"),
        "access_token": os.getenv("SHOPIFY_TOKEN"),
        "sentos_api_url": os.getenv("SENTOS_API_URL"),
        "sentos_api_key": os.getenv("SENTOS_API_KEY"),
        "sentos_api_secret": os.getenv("SENTOS_API_SECRET"),
        "sentos_cookie": os.getenv("SENTOS_COOKIE", ""),
    }

    # Ayarların eksik olup olmadığını kontrol et
    missing_keys = [key for key, value in config.items() if not value and key != "sentos_cookie"]
    if missing_keys:
        logging.error(f"Eksik ayarlar (GitHub Secrets): {', '.join(missing_keys)}")
        sys.exit(1)

    try:
        # GÜNCELLEME: `run_sync_for_cron` fonksiyonunun yaptığı işi buraya taşıdık.
        # Bu, `AttributeError` hatasını ortadan kaldırır.
        
        # 1. Callback fonksiyonunu tanımla (loglama için)
        def cron_progress_callback(update):
            if 'message' in update:
                logging.info(update['message'])
            if 'log_detail' in update:
                # HTML etiketlerini temizleyerek log'a yaz
                clean_log = re.sub('<[^<]+?>', '', update['log_detail'])
                logging.info(clean_log.strip())

        # 2. Durdurma olayını tanımla (cron'da kullanılmasa da fonksiyon bunu bekler)
        stop_event = threading.Event()
        
        # 3. Ana senkronizasyon fonksiyonunu doğrudan çağır
        sync_products_from_sentos_api(
            store_url=config["store_url"],
            access_token=config["access_token"],
            sentos_api_url=config["sentos_api_url"],
            sentos_api_key=config["sentos_api_key"],
            sentos_api_secret=config["sentos_api_secret"],
            sentos_cookie=config["sentos_cookie"],
            test_mode=False,  # Zamanlanmış görevler her zaman tam çalışmalıdır.
            progress_callback=cron_progress_callback,
            stop_event=stop_event,
            sync_mode=sync_mode_to_run,
            max_workers=4
        )
        
        logging.info(f"Zamanlanmış senkronizasyon (Mod: {sync_mode_to_run}) başarıyla tamamlandı.")
    except Exception as e:
        logging.critical(f"Senkronizasyon sırasında ölümcül bir hata oluştu: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()