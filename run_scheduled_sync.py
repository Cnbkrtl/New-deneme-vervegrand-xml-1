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
    logging.info("GitHub Actions tarafından tetiklenen zamanlanmış senkronizasyon başlıyor...")

    # Gerekli ayarları GitHub Secrets'tan oku
    config = {
        "store_url": os.getenv("SHOPIFY_STORE"),
        "access_token": os.getenv("SHOPIFY_TOKEN"),
        "sentos_api_url": os.getenv("SENTOS_API_URL"),
        "sentos_api_key": os.getenv("SENTOS_API_KEY"),
        "sentos_api_secret": os.getenv("SENTOS_API_SECRET"),
        "sentos_cookie": os.getenv("SENTOS_COOKIE", ""), # Cookie opsiyonel
    }

    # Ayarların eksik olup olmadığını kontrol et
    missing_keys = [key for key, value in config.items() if not value and key != "sentos_cookie"]
    if missing_keys:
        logging.error(f"Eksik ayarlar (GitHub Secrets): {', '.join(missing_keys)}")
        sys.exit(1) # Hata ile çık

    try:
        # Cron için özel olarak tasarlanmış senkronizasyon fonksiyonunu çağır
        shopify_sync.run_sync_for_cron(
            store_url=config["store_url"],
            access_token=config["access_token"],
            sentos_api_url=config["sentos_api_url"],
            sentos_api_key=config["sentos_api_key"],
            sentos_api_secret=config["sentos_api_secret"],
            sentos_cookie=config["sentos_cookie"],
            sync_mode="Stock & Variants Only", # Zamanlanmış görevler için varsayılan mod
            max_workers=4 # GitHub Actions güçlü olduğu için worker sayısını artırabiliriz
        )
        logging.info("Zamanlanmış senkronizasyon başarıyla tamamlandı.")
    except Exception as e:
        logging.critical(f"Senkronizasyon sırasında ölümcül bir hata oluştu: {e}", exc_info=True)
        sys.exit(1) # Hata ile çık

if __name__ == "__main__":
    main()