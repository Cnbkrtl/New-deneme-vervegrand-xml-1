# operations/media_sync.py (Güvenlik Artırılmış Sürüm)

import logging
import time

def sync_media(shopify_api, sentos_api, product_gid, sentos_product, set_alt_text=False, force_update=False):
    """
    Bir ürünün medya dosyalarını senkronize eder.
    
    Args:
        force_update (bool): True ise cookie olmasa bile güncelleme yapmaya çalışır
    """
    changes = []
    product_title = sentos_product.get('name', '').strip()
    product_id = sentos_product.get('id')
    
    # Güvenlik kontrolü: Ürün ID'si olmalı
    if not product_id:
        changes.append("❌ Ürün ID'si bulunamadı, medya sync atlandı.")
        return changes
    
    # Sentos'tan sıralı görsel URL'lerini al
    try:
        sentos_ordered_urls = sentos_api.get_ordered_image_urls(product_id)
        logging.info(f"Ürün {product_id} için Sentos'tan {len(sentos_ordered_urls) if sentos_ordered_urls else 0} görsel URL'si alındı")
    except Exception as e:
        logging.error(f"Sentos'tan görsel URL'leri alınırken hata: {e}")
        sentos_ordered_urls = None
    
    # Cookie eksikse ve force_update False ise güvenli şekilde atla
    if sentos_ordered_urls is None:
        if not force_update:
            changes.append("⚠️ Medya senkronizasyonu atlandı (Cookie eksik veya hata)")
            return changes
        else:
            # Force update modunda, ürünün kendi görsellerini kullanmaya çalış
            sentos_ordered_urls = _get_fallback_images(sentos_product)
            if not sentos_ordered_urls:
                changes.append("⚠️ Cookie eksik ve alternatif görsel bulunamadı")
                return changes
    
    # Mevcut Shopify medyalarını al
    try:
        initial_shopify_media = shopify_api.get_product_media_details(product_gid)
        logging.info(f"Shopify'da {len(initial_shopify_media)} mevcut medya bulundu")
    except Exception as e:
        logging.error(f"Shopify medya detayları alınırken hata: {e}")
        changes.append(f"❌ Shopify medya bilgileri alınamadı: {e}")
        return changes
    
    # KRİTİK GÜVENLİK KONTROLÜ: Sentos'tan görsel gelmezse SİLME!
    if not sentos_ordered_urls or len(sentos_ordered_urls) == 0:
        logging.warning(f"Ürün {product_id} için Sentos'tan görsel URL'si gelmedi. GÜVENLİK SEBEBİYLE mevcut görseller korunacak.")
        changes.append("⚠️ Sentos'tan görsel bilgisi alınamadı - mevcut görseller korundu")
        return changes
    
    # Mevcut Shopify görsellerini URL'lere göre haritala
    shopify_src_map = {m['originalSrc']: m for m in initial_shopify_media if m.get('originalSrc')}
    
    # Hangi görsellerin silinmesi ve eklenmesi gerektiğini hesapla
    media_ids_to_delete = [media['id'] for src, media in shopify_src_map.items() if src not in sentos_ordered_urls]
    urls_to_add = [url for url in sentos_ordered_urls if url not in shopify_src_map]
    
    logging.info(f"Silinecek medya: {len(media_ids_to_delete)}, Eklenecek URL: {len(urls_to_add)}")
    
    media_changed = False
    
    # Yeni görseller ekle
    if urls_to_add:
        try:
            success_count = _add_media(shopify_api, product_gid, urls_to_add, product_title, set_alt_text)
            changes.append(f"✅ {success_count}/{len(urls_to_add)} yeni görsel eklendi")
            media_changed = True
        except Exception as e:
            logging.error(f"Medya ekleme hatası: {e}")
            changes.append(f"❌ Görsel ekleme hatası: {e}")
    
    # Eski görselleri sil (SADECE yenileri başarıyla eklendikten sonra)
    if media_ids_to_delete and (urls_to_add == [] or media_changed):
        try:
            _delete_media(shopify_api, product_gid, media_ids_to_delete)
            changes.append(f"🗑️ {len(media_ids_to_delete)} eski görsel silindi")
            media_changed = True
        except Exception as e:
            logging.error(f"Medya silme hatası: {e}")
            changes.append(f"❌ Eski görsel silme hatası: {e}")
    
    # Görsel sıralamasını güncelle
    if media_changed:
        changes.append("🔄 Görsel sırası güncelleniyor...")
        time.sleep(5)  # Medyanın işlenmesi için bekle
        
        try:
            final_shopify_media = shopify_api.get_product_media_details(product_gid)
            final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
            ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]
            
            if len(ordered_media_ids) > 1:
                _reorder_media(shopify_api, product_gid, ordered_media_ids)
                changes.append("📐 Görsel sıralaması güncellendi")
        except Exception as e:
            logging.error(f"Medya sıralama hatası: {e}")
            changes.append(f"❌ Sıralama hatası: {e}")
    
    if not changes:
        changes.append("✅ Görseller kontrol edildi (Değişiklik gerekmedi)")
    
    return changes

def _get_fallback_images(sentos_product):
    """Cookie olmadığında ürünün temel görsel bilgilerini kullanmaya çalışır"""
    fallback_urls = []
    
    # Ana ürün resmini kontrol et
    if main_image := sentos_product.get('image'):
        fallback_urls.append(main_image)
    
    # Varyant resimlerini kontrol et
    for variant in sentos_product.get('variants', []):
        if variant_image := variant.get('image'):
            fallback_urls.append(variant_image)
    
    # Benzersiz URL'leri döndür
    return list(dict.fromkeys(fallback_urls))

def _add_media(shopify_api, product_gid, urls, product_title, set_alt_text):
    """Medya ekleme fonksiyonu - başarı sayısını döndürür"""
    if not urls:
        return 0
    
    media_input = []
    for url in urls:
        alt_text = product_title if set_alt_text else url
        media_input.append({
            "originalSource": url, 
            "alt": alt_text, 
            "mediaContentType": "IMAGE"
        })
    
    success_count = 0
    # 5'li gruplar halinde ekle (daha güvenli)
    for i in range(0, len(media_input), 5):
        batch = media_input[i:i + 5]
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
            if result.get('productCreateMedia', {}).get('mediaUserErrors'):
                errors = result['productCreateMedia']['mediaUserErrors']
                logging.error(f"Medya ekleme hataları: {errors}")
            else:
                success_count += len(batch)
                logging.info(f"Batch {i//5 + 1}: {len(batch)} medya başarıyla eklendi")
            
            time.sleep(1)  # Rate limit koruması
            
        except Exception as e:
            logging.error(f"Medya batch {i//5 + 1} eklenirken hata: {e}")
    
    return success_count

def _delete_media(shopify_api, product_id, media_ids):
    """Güvenli medya silme fonksiyonu"""
    if not media_ids: 
        return
    
    # Tek seferde çok fazla silmeyi önle
    if len(media_ids) > 20:
        logging.warning(f"Çok fazla medya silinmeye çalışılıyor ({len(media_ids)}). Güvenlik sebebiyle ilk 20'si silinecek.")
        media_ids = media_ids[:20]
    
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
        if result.get('productDeleteMedia', {}).get('userErrors'):
            errors = result['productDeleteMedia']['userErrors']
            logging.error(f"Medya silme hataları: {errors}")
        else:
            deleted_count = len(result.get('productDeleteMedia', {}).get('deletedMediaIds', []))
            logging.info(f"{deleted_count} medya başarıyla silindi")
            
    except Exception as e:
        logging.error(f"Medya silinirken hata: {e}")
        raise e

def _reorder_media(shopify_api, product_id, media_ids):
    """Medya sıralaması fonksiyonu"""
    if not media_ids or len(media_ids) < 2: 
        return
    
    moves = [{"id": media_id, "newPosition": str(i)} for i, media_id in enumerate(media_ids) if media_id]
    
    if not moves:
        logging.warning("Sıralanacak medya ID'si bulunamadı")
        return
    
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
        if result.get('productReorderMedia', {}).get('userErrors'):
            errors = result['productReorderMedia']['userErrors']
            logging.error(f"Medya sıralama hataları: {errors}")
        else:
            logging.info(f"{len(moves)} medya başarıyla sıralandı")
            
    except Exception as e:
        logging.error(f"Medya yeniden sıralanırken hata: {e}")
        raise e