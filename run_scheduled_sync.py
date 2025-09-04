import os
import logging
import sys

# Proje yolunu Python path'ine ekle
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

import shopify_sync

# Temel loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    Ortam değişkenlerinden (GitHub Secrets) ayarları okur ve
    zamanlanmış senkronizasyon görevini başlatır.
    """
    
    # GÜNCELLEME: Hangi modda çalışacağını ortam değişkeninden oku.
    # Eğer SYNC_MODE belirtilmemişse, varsayılan olarak "Stock & Variants Only" kullan.
    sync_mode_to_run = os.getenv("SYNC_MODE", "Stock & Variants Only")

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
        # Cron için özel olarak tasarlanmış senkronizasyon fonksiyonunu çağır
        shopify_sync.run_sync_for_cron(
            store_url=config["store_url"],
            access_token=config["access_token"],
            sentos_api_url=config["sentos_api_url"],
            sentos_api_key=config["sentos_api_key"],
            sentos_api_secret=config["sentos_api_secret"],
            sentos_cookie=config["sentos_cookie"],
            sync_mode=sync_mode_to_run, # GÜNCELLEME: Modu buraya iletiyoruz
            max_workers=4
        )
        logging.info(f"Zamanlanmış senkronizasyon (Mod: {sync_mode_to_run}) başarıyla tamamlandı.")
    except Exception as e:
        logging.critical(f"Senkronizasyon sırasında ölümcül bir hata oluştu: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()