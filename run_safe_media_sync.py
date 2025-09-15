#!/usr/bin/env python3
# run_safe_media_sync.py (GitHub Actions için güvenli medya sync)

import os
import sys
import logging
import time
from datetime import datetime

# Logging ayarla
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_results.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    """GitHub Actions için güvenli medya senkronizasyonu"""
    
    # Environment variables kontrolü
    required_vars = ['SHOPIFY_STORE', 'SHOPIFY_TOKEN', 'SENTOS_API_URL', 'SENTOS_API_KEY', 'SENTOS_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logging.error(f"Eksik environment variables: {missing_vars}")
        sys.exit(1)
    
    # Güvenlik ayarları
    sync_mode = os.getenv('SYNC_MODE', 'test')
    force_update = os.getenv('FORCE_UPDATE', 'false').lower() == 'true'
    max_products = int(os.getenv('MAX_PRODUCTS', '5'))
    
    logging.info(f"=== GÜVENLİ MEDYA SYNC BAŞLADI ===")
    logging.info(f"Mod: {sync_mode}")
    logging.info(f"Max ürün: {max_products}")
    logging.info(f"Force update: {force_update}")
    logging.info(f"Cookie mevcut: {'Evet' if os.getenv('SENTOS_COOKIE') else 'Hayır'}")
    
    try:
        # API bağlantılarını başlat
        from connectors.shopify_api import ShopifyAPI
        from connectors.sentos_api import SentosAPI
        from operations.media_sync import sync_media
        
        shopify_api = ShopifyAPI(os.getenv('SHOPIFY_STORE'), os.getenv('SHOPIFY_TOKEN'))
        sentos_api = SentosAPI(
            os.getenv('SENTOS_API_URL'),
            os.getenv('SENTOS_API_KEY'), 
            os.getenv('SENTOS_API_SECRET'),
            os.getenv('SENTOS_COOKIE')
        )
        
        # Sentos'tan ürünleri al (sınırlı sayıda)
        logging.info("Sentos'tan ürünler çekiliyor...")
        
        def progress_callback(update):
            logging.info(f"İlerleme: {update.get('message', 'İşleniyor...')}")
        
        all_products = sentos_api.get_all_products(progress_callback=progress_callback)
        
        if not all_products:
            logging.error("Sentos'tan ürün alınamadı")
            sys.exit(1)
        
        # Ürün sayısını sınırla
        products_to_sync = all_products[:max_products]
        logging.info(f"İşlenecek ürün sayısı: {len(products_to_sync)}")
        
        # Stats
        stats = {
            'total': len(products_to_sync),
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        start_time = time.time()
        
        # Her ürün için medya sync
        for i, sentos_product in enumerate(products_to_sync, 1):
            product_sku = sentos_product.get('sku', 'N/A')
            product_name = sentos_product.get('name', 'İsimsiz')
            
            logging.info(f"[{i}/{len(products_to_sync)}] İşleniyor: {product_sku} - {product_name}")
            
            try:
                # Shopify'da ürünü bul
                shopify_products = shopify_api.get_variant_ids_by_skus([product_sku], search_by_product_sku=True)
                
                if not shopify_products:
                    logging.warning(f"Ürün Shopify'da bulunamadı: {product_sku}")
                    stats['skipped'] += 1
                    continue
                
                # İlk eşleşen ürünün product_id'sini al
                product_gid = list(shopify_products.values())[0]['product_id']
                
                # Medya senkronizasyonu yap - GÜVENLİ MODDA
                changes = sync_media(
                    shopify_api=shopify_api,
                    sentos_api=sentos_api, 
                    product_gid=product_gid,
                    sentos_product=sentos_product,
                    set_alt_text=True,  # SEO için alt text ekle
                    force_update=force_update
                )
                
                if changes:
                    logging.info(f"✅ {product_sku}: {', '.join(changes)}")
                    stats['success'] += 1
                else:
                    logging.info(f"⭕ {product_sku}: Değişiklik gerekmedi")
                    stats['skipped'] += 1
                
                stats['processed'] += 1
                
                # Rate limit koruması
                time.sleep(2)
                
            except Exception as e:
                logging.error(f"❌ {product_sku} işlenirken hata: {e}")
                stats['failed'] += 1
                
                # Çok fazla hata varsa dur
                if stats['failed'] > 5:
                    logging.error("Çok fazla hata oluştu, işlem durduruluyor")
                    break
        
        # Sonuç raporu
        duration = time.time() - start_time
        logging.info(f"=== SYNC TAMAMLANDI ===")
        logging.info(f"Süre: {duration:.1f} saniye")
        logging.info(f"Toplam: {stats['total']}")
        logging.info(f"İşlenen: {stats['processed']}")
        logging.info(f"Başarılı: {stats['success']}")
        logging.info(f"Başarısız: {stats['failed']}")
        logging.info(f"Atlanan: {stats['skipped']}")
        
        # Başarı oranı kontrolü
        if stats['failed'] > stats['success']:
            logging.error("Başarısız işlem sayısı başarılı olanlardan fazla!")
            sys.exit(1)
        
        logging.info("✅ Medya senkronizasyonu başarıyla tamamlandı")
        
    except Exception as e:
        logging.error(f"Ana süreçte kritik hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()