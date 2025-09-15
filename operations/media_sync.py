# operations/media_sync.py (Debug ve Düzeltme Sürümü)

import logging
import time

def sync_media(shopify_api, sentos_api, product_gid, sentos_product, set_alt_text=False, force_update=False):
    """
    Bir ürünün medya dosyalarını senkronize eder.
    DEBUG: Detaylı log çıktıları eklendi
    """
    changes = []
    product_title = sentos_product.get('name', '').strip()
    product_id = sentos_product.get('id')
    
    logging.info(f"🔍 MEDYA SYNC BAŞLADI - Ürün ID: {product_id}, Başlık: {product_title}")
    
    # Güvenlik kontrolü: Ürün ID'si olmalı
    if not product_id:
        changes.append("❌ Ürün ID'si bulunamadı, medya sync atlandı.")
        logging.error("❌ Ürün ID'si bulunamadı!")
        return changes
    
    # DEBUG: Cookie durumunu kontrol et
    has_cookie = sentos_api.api_cookie is not None and sentos_api.api_cookie.strip() != ""
    logging.info(f"🔐 Cookie durumu: {'Mevcut' if has_cookie else 'Eksik'}")
    
    # Sentos'tan sıralı görsel URL'lerini al
    sentos_ordered_urls = None
    try:
        logging.info(f"📸 Sentos'tan görsel URL'leri alınıyor...")
        sentos_ordered_urls = sentos_api.get_ordered_image_urls(product_id)
        logging.info(f"📋 Sentos'tan alınan URL sayısı: {len(sentos_ordered_urls) if sentos_ordered_urls else 0}")
        
        # DEBUG: URL'leri logla
        if sentos_ordered_urls:
            for i, url in enumerate(sentos_ordered_urls[:3]):  # İlk 3'ünü göster
                logging.info(f"  📸 URL {i+1}: {url}")
        
    except Exception as e:
        logging.error(f"❌ Sentos'tan görsel URL'leri alınırken hata: {e}")
        sentos_ordered_urls = None
    
    # Cookie eksikse alternatif görsel kaynaklarını dene
    if sentos_ordered_urls is None or len(sentos_ordered_urls) == 0:
        logging.warning("⚠️ Sentos'tan görsel URL'si alınamadı, alternatif kaynaklara bakılıyor...")
        
        # Alternatif 1: Ürünün kendi görsel bilgilerini kullan
        fallback_urls = _get_fallback_images(sentos_product)
        if fallback_urls:
            logging.info(f"🔄 Alternatif kaynaklardan {len(fallback_urls)} görsel bulundu")
            sentos_ordered_urls = fallback_urls
        else:
            logging.warning("⚠️ Hiçbir alternatif görsel kaynağı bulunamadı")
    
    # KRITIK: Hala görsel yoksa ve force_update False ise güvenli çık
    if not sentos_ordered_urls or len(sentos_ordered_urls) == 0:
        if not force_update:
            changes.append("⚠️ Sentos'tan görsel bilgisi alınamadı - mevcut görseller korundu")
            logging.warning("⚠️ Görsel bulunamadı ve force_update=False, güvenli çıkış yapılıyor")
            return changes
        else:
            changes.append("❌ Force update aktif ama hiç görsel bulunamadı")
            logging.error("❌ Force update aktif ama hiç görsel bulunamadı")
            return changes
    
    # Mevcut Shopify medyalarını al
    try:
        logging.info("🛍️ Shopify'daki mevcut görseller alınıyor...")
        initial_shopify_media = shopify_api.get_product_media_details(product_gid)
        logging.info(f"📊 Shopify'da {len(initial_shopify_media)} mevcut medya bulundu")
        
        # DEBUG: Mevcut medyaları logla
        for i, media in enumerate(initial_shopify_media[:3]):
            logging.info(f"  🛍️ Mevcut {i+1}: {media.get('originalSrc', 'URL yok')}")
            
    except Exception as e:
        logging.error(f"❌ Shopify medya detayları alınırken hata: {e}")
        changes.append(f"❌ Shopify medya bilgileri alınamadı: {e}")
        return changes
    
    # Mevcut Shopify görsellerini URL'lere göre haritala
    shopify_src_map = {m['originalSrc']: m for m in initial_shopify_media if m.get('originalSrc')}
    
    # Hangi görsellerin silinmesi ve eklenmesi gerektiğini hesapla
    media_ids_to_delete = [media['id'] for src, media in shopify_src_map.items() if src not in sentos_ordered_urls]
    urls_to_add = [url for url in sentos_ordered_urls if url not in shopify_src_map]
    
    logging.info(f"📊 KARŞILAŞTIRMA SONUCU:")
    logging.info(f"  ➕ Eklenecek URL: {len(urls_to_add)}")
    logging.info(f"  ➖ Silinecek medya: {len(media_ids_to_delete)}")
    
    # DEBUG: Eklenecek URL'leri detaylandır
    if urls_to_add:
        logging.info("➕ EKLENECEK URL'LER:")
        for i, url in enumerate(urls_to_add[:3]):
            logging.info(f"    {i+1}. {url}")
    
    # DEBUG: Silinecek medyaları detaylandır
    if media_ids_to_delete:
        logging.info("➖ SİLİNECEK MEDYALAR:")
        for i, media_id in enumerate(media_ids_to_delete[:3]):
            logging.info(f"    {i+1}. {media_id}")
    
    media_changed = False
    
    # Yeni görseller ekle
    if urls_to_add:
        try:
            logging.info(f"➕ {len(urls_to_add)} yeni görsel ekleniyor...")
            success_count = _add_media(shopify_api, product_gid, urls_to_add, product_title, set_alt_text)
            changes.append(f"✅ {success_count}/{len(urls_to_add)} yeni görsel eklendi")
            logging.info(f"✅ {success_count}/{len(urls_to_add)} görsel başarıyla eklendi")
            media_changed = True
        except Exception as e:
            logging.error(f"❌ Medya ekleme hatası: {e}")
            changes.append(f"❌ Görsel ekleme hatası: {e}")
    else:
        logging.info("ℹ️ Eklenecek yeni görsel yok")
    
    # Eski görselleri sil (SADECE yenileri başarıyla eklendikten sonra)
    if media_ids_to_delete and (not urls_to_add or media_changed):
        try:
            logging.info(f"➖ {len(media_ids_to_delete)} eski görsel siliniyor...")
            _delete_media(shopify_api, product_gid, media_ids_to_delete)
            changes.append(f"🗑️ {len(media_ids_to_delete)} eski görsel silindi")
            logging.info(f"✅ {len(media_ids_to_delete)} görsel başarıyla silindi")
            media_changed = True
        except Exception as e:
            logging.error(f"❌ Medya silme hatası: {e}")
            changes.append(f"❌ Eski görsel silme hatası: {e}")
    else:
        if media_ids_to_delete:
            logging.info("ℹ️ Yeni görseller eklenemediği için eskiler silinmedi")
        else:
            logging.info("ℹ️ Silinecek eski görsel yok")
    
    # Görsel sıralamasını güncelle
    if media_changed and len(sentos_ordered_urls) > 1:
        logging.info("🔄 Görsel sıralaması güncelleniyor...")
        changes.append("🔄 Görsel sırası güncelleniyor...")
        time.sleep(5)  # Medyanın işlenmesi için bekle
        
        try:
            final_shopify_media = shopify_api.get_product_media_details(product_gid)
            final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
            ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]
            
            if len(ordered_media_ids) > 1:
                _reorder_media(shopify_api, product_gid, ordered_media_ids)
                changes.append("🔀 Görsel sıralaması güncellendi")
                logging.info("✅ Görsel sıralaması başarıyla güncellendi")
        except Exception as e:
            logging.error(f"❌ Medya sıralama hatası: {e}")
            changes.append(f"❌ Sıralama hatası: {e}")
    
    # Sonuç değerlendirmesi
    if not changes:
        # Bu durumda gerçekten hiçbir değişiklik olmamış
        changes.append("✅ Görseller kontrol edildi (Değişiklik gerekmedi)")
        logging.info("ℹ️ Görsel karşılaştırması yapıldı, değişiklik gerekmedi")
    elif not media_changed:
        # İşlem denenmiş ama başarısız
        changes.append("⚠️ Görsel güncelleme denendi ama başarısız")
        logging.warning("⚠️ Görsel güncelleme işlemleri başarısız oldu")
    
    logging.info(f"🏁 MEDYA SYNC TAMAMLANDI - Toplam değişiklik: {len(changes)}")
    return changes

def _get_fallback_images(sentos_product):
    """Cookie olmadığında ürünün temel görsel bilgilerini kullanmaya çalışır"""
    fallback_urls = []
    
    logging.info("🔍 Alternatif görsel kaynakları aranıyor...")
    
    # Ana ürün resmini kontrol et
    if main_image := sentos_product.get('image'):
        fallback_urls.append(main_image)
        logging.info(f"📸 Ana ürün resmi bulundu: {main_image}")
    
    # Varyant resimlerini kontrol et
    for i, variant in enumerate(sentos_product.get('variants', [])):
        if variant_image := variant.get('image'):
            fallback_urls.append(variant_image)
            logging.info(f"📸 Varyant {i+1} resmi bulundu: {variant_image}")
    
    # Diğer potansiyel resim alanlarını kontrol et
    for field in ['image_url', 'main_image', 'featured_image', 'thumbnail']:
        if image_url := sentos_product.get(field):
            fallback_urls.append(image_url)
            logging.info(f"📸 {field} alanında resim bulundu: {image_url}")
    
    # Benzersiz URL'leri döndür
    unique_urls = list(dict.fromkeys(fallback_urls))
    logging.info(f"📊 Toplam {len(unique_urls)} benzersiz alternatif URL bulundu")
    
    return unique_urls

def _add_media(shopify_api, product_gid, urls, product_title, set_alt_text):
    """Medya ekleme fonksiyonu - başarı sayısını döndürür"""
    if not urls:
        return 0
    
    logging.info(f"➕ {len(urls)} URL için medya ekleme başlatılıyor...")
    
    media_input = []
    for i, url in enumerate(urls):
        alt_text = product_title if set_alt_text else url
        media_input.append({
            "originalSource": url, 
            "alt": alt_text, 
            "mediaContentType": "IMAGE"
        })
        logging.info(f"📝 Medya {i+1} hazırlandı: {url[:50]}... (alt: {alt_text[:30]}...)")
    
    success_count = 0
    # 5'li gruplar halinde ekle (daha güvenli)
    for i in range(0, len(media_input), 5):
        batch = media_input[i:i + 5]
        batch_num = i//5 + 1
        logging.info(f"📦 Batch {batch_num} işleniyor ({len(batch)} medya)...")
        
        try:
            query = """
            mutation productCreateMedia($pId: ID!, $media: [CreateMediaInput!]!) { 
                productCreateMedia(productId: $pId, media: $media) { 
                    media { id } 
                    mediaUserErrors { field message } 
                } 
            }
            """
            result = shopify_api.execute_graphql(query, {'pId': product_gid, 'media': batch})
            
            # Hata kontrolü
            media_errors = result.get('productCreateMedia', {}).get('mediaUserErrors', [])
            if media_errors:
                logging.error(f"❌ Batch {batch_num} medya ekleme hataları: {media_errors}")
                for error in media_errors:
                    logging.error(f"   - {error.get('field', 'Unknown')}: {error.get('message', 'Unknown error')}")
            else:
                success_count += len(batch)
                logging.info(f"✅ Batch {batch_num}: {len(batch)} medya başarıyla eklendi")
            
            time.sleep(1)  # Rate limit koruması
            
        except Exception as e:
            logging.error(f"❌ Medya batch {batch_num} eklenirken hata: {e}")
    
    logging.info(f"📊 Medya ekleme tamamlandı: {success_count}/{len(urls)} başarılı")
    return success_count

def _delete_media(shopify_api, product_id, media_ids):
    """Güvenli medya silme fonksiyonu"""
    if not media_ids: 
        return
    
    # Tek seferde çok fazla silmeyi önle
    if len(media_ids) > 20:
        logging.warning(f"⚠️ Çok fazla medya silinmeye çalışılıyor ({len(media_ids)}). Güvenlik sebebiyle ilk 20'si silinecek.")
        media_ids = media_ids[:20]
    
    logging.info(f"🗑️ {len(media_ids)} medya siliniyor...")
    
    query = """
    mutation pDM($pId: ID!, $mIds: [ID!]!) { 
        productDeleteMedia(productId: $pId, mediaIds: $mIds) { 
            deletedMediaIds 
            userErrors { field message } 
        } 
    }
    """
    try:
        result = shopify_api.execute_graphql(query, {'pId': product_id, 'mIds': media_ids})
        
        # Hata kontrolü
        delete_errors = result.get('productDeleteMedia', {}).get('userErrors', [])
        if delete_errors:
            logging.error(f"❌ Medya silme hataları: {delete_errors}")
            for error in delete_errors:
                logging.error(f"   - {error.get('field', 'Unknown')}: {error.get('message', 'Unknown error')}")
        else:
            deleted_count = len(result.get('productDeleteMedia', {}).get('deletedMediaIds', []))
            logging.info(f"✅ {deleted_count} medya başarıyla silindi")
            
    except Exception as e:
        logging.error(f"❌ Medya silinirken hata: {e}")
        raise e

def _reorder_media(shopify_api, product_id, media_ids):
    """Medya sıralaması fonksiyonu"""
    if not media_ids or len(media_ids) < 2: 
        return
    
    moves = [{"id": media_id, "newPosition": str(i)} for i, media_id in enumerate(media_ids) if media_id]
    
    if not moves:
        logging.warning("⚠️ Sıralanacak medya ID'si bulunamadı")
        return
    
    logging.info(f"🔀 {len(moves)} medya yeniden sıralanıyor...")
    
    query = """
    mutation pRM($id: ID!, $moves: [MoveInput!]!) { 
        productReorderMedia(id: $id, moves: $moves) { 
            userErrors { field message } 
        } 
    }
    """
    try:
        result = shopify_api.execute_graphql(query, {'id': product_id, 'moves': moves})
        
        # Hata kontrolü
        reorder_errors = result.get('productReorderMedia', {}).get('userErrors', [])
        if reorder_errors:
            logging.error(f"❌ Medya sıralama hataları: {reorder_errors}")
            for error in reorder_errors:
                logging.error(f"   - {error.get('field', 'Unknown')}: {error.get('message', 'Unknown error')}")
        else:
            logging.info(f"✅ {len(moves)} medya başarıyla sıralandı")
            
    except Exception as e:
        logging.error(f"❌ Medya yeniden sıralanırken hata: {e}")
        raise e