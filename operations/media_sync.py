# operations/media_sync.py - Eski kodun mantığıyla düzeltilmiş

import logging
import time

def sync_media(shopify_api, sentos_api, product_gid, sentos_product, set_alt_text=False, force_update=False):
    """
    ESKİ KODDAN UYARLANMIŞ ÇALIŞAN VERSİYON
    Eski _sync_product_media fonksiyonunun aynısı
    """
    changes = []
    product_title = sentos_product.get('name', '').strip()
    product_id = sentos_product.get('id')
    
    logging.info(f"Medya senkronizasyonu başlıyor - Ürün: {product_title} (ID: {product_id})")
    
    # Sentos'tan sıralı görsel URL'lerini al (eski mantık)
    sentos_ordered_urls = sentos_api.get_ordered_image_urls(product_id)
    
    # KRİTİK: Eski kodda None dönerse cookie eksik anlamına gelir
    if sentos_ordered_urls is None:
        changes.append("Medya senkronizasyonu atlandı (Cookie eksik).")
        logging.warning(f"Cookie eksikliği nedeniyle medya sync atlandı - Ürün ID: {product_id}")
        return changes
    
    # Mevcut Shopify medyalarını al
    try:
        initial_shopify_media = shopify_api.get_product_media_details(product_gid)
        logging.info(f"Shopify'da {len(initial_shopify_media)} mevcut medya bulundu")
    except Exception as e:
        logging.error(f"Shopify medya bilgileri alınamadı: {e}")
        changes.append(f"Hata: Shopify medya bilgileri alınamadı - {e}")
        return changes
    
    # Eğer Sentos'tan hiç görsel gelmezse, Shopify'daki tüm görselleri sil
    if not sentos_ordered_urls:
        logging.info("Sentos'tan görsel gelmedi, Shopify görselleri silinecek")
        if media_ids_to_delete := [m['id'] for m in initial_shopify_media]:
            shopify_api.delete_product_media(product_gid, media_ids_to_delete)
            changes.append(f"{len(media_ids_to_delete)} Shopify görseli silindi.")
        return changes
    
    # Mevcut Shopify görsellerini URL'lere göre haritala
    shopify_src_map = {m['originalSrc']: m for m in initial_shopify_media if m.get('originalSrc')}
    
    # Hangi görsellerin silinmesi ve eklenmesi gerektiğini hesapla
    media_ids_to_delete = [media['id'] for src, media in shopify_src_map.items() if src not in sentos_ordered_urls]
    urls_to_add = [url for url in sentos_ordered_urls if url not in shopify_src_map]
    
    logging.info(f"Medya karşılaştırması: {len(urls_to_add)} eklenecek, {len(media_ids_to_delete)} silinecek")
    
    media_changed = False
    
    # Yeni görseller ekle
    if urls_to_add:
        changes.append(f"{len(urls_to_add)} yeni görsel eklendi.")
        _add_new_media_to_product(shopify_api, product_gid, urls_to_add, product_title, set_alt_text)
        media_changed = True
        
    # Eski görselleri sil
    if media_ids_to_delete:
        changes.append(f"{len(media_ids_to_delete)} eski görsel silindi.")
        shopify_api.delete_product_media(product_gid, media_ids_to_delete)
        media_changed = True
        
    # Görsel sıralamasını güncelle (eski mantık)
    if media_changed:
        changes.append("Görsel sırası güncellendi.")
        time.sleep(10)  # Medyanın işlenmesi için bekle
        
        # Yeniden düzenlenmiş medya listesini al
        final_shopify_media = shopify_api.get_product_media_details(product_gid)
        final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
        ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]

        if len(ordered_media_ids) < len(sentos_ordered_urls):
            logging.warning(f"Alt etiketi eşleştirme sorunu: {len(sentos_ordered_urls)} resim beklenirken {len(ordered_media_ids)} ID bulundu. Sıralama eksik olabilir.")

        shopify_api.reorder_product_media(product_gid, ordered_media_ids)
    
    # Hiç değişiklik olmadıysa
    if not changes and not media_changed:
        changes.append("Resimler kontrol edildi (Değişiklik yok).")
        
    logging.info(f"Medya senkronizasyonu tamamlandı - {len(changes)} değişiklik")
    return changes


def _add_new_media_to_product(shopify_api, product_gid, urls_to_add, product_title, set_alt_text=False):
    """
    ESKİ KODDAN ALINMIŞ MEDYA EKLEME FONKSİYONU
    """
    if not urls_to_add: 
        return
        
    logging.info(f"{len(urls_to_add)} yeni medya ekleniyor...")
    
    media_input = []
    for url in urls_to_add:
        alt_text = product_title if set_alt_text else url
        media_input.append({
            "originalSource": url, 
            "alt": alt_text, 
            "mediaContentType": "IMAGE"
        })
    
    # 10'lu gruplar halinde ekle (eski kod mantığı)
    for i in range(0, len(media_input), 10):
        batch = media_input[i:i + 10]
        try:
            query = """
            mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) { 
                productCreateMedia(productId: $productId, media: $media) { 
                    media { id } 
                    mediaUserErrors { field message } 
                } 
            }
            """
            result = shopify_api.execute_graphql(query, {'productId': product_gid, 'media': batch})
            
            # Hata kontrolü
            if errors := result.get('productCreateMedia', {}).get('mediaUserErrors', []):
                logging.error(f"Medya ekleme hataları: {errors}")
            else:
                logging.info(f"Batch {i//10 + 1}: {len(batch)} medya başarıyla eklendi")
                
        except Exception as e:
            logging.error(f"Medya batch {i//10 + 1} eklenirken hata: {e}")


# ShopifyAPI sınıfına eksik fonksiyonları ekle
def get_product_media_details(shopify_api, product_gid):
    """
    ESKİ KODDAK _get_product_media_details FONKSİYONU
    ShopifyAPI sınıfına eklenmesi gereken fonksiyon
    """
    try:
        query = """
        query getProductMedia($id: ID!) {
            product(id: $id) {
                media(first: 250) {
                    edges {
                        node {
                            id
                            alt
                            ... on MediaImage {
                                image {
                                    originalSrc
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        result = shopify_api.execute_graphql(query, {"id": product_gid})
        media_edges = result.get("product", {}).get("media", {}).get("edges", [])
        
        media_details = []
        for edge in media_edges:
            node = edge.get('node')
            if node:
                media_details.append({
                    'id': node['id'],
                    'alt': node.get('alt'),
                    'originalSrc': node.get('image', {}).get('originalSrc')
                })
        
        logging.info(f"Ürün {product_gid} için {len(media_details)} mevcut medya bulundu.")
        return media_details
        
    except Exception as e:
        logging.error(f"Mevcut medya detayları alınırken hata: {e}")
        return []


def delete_product_media(shopify_api, product_id, media_ids):
    """
    ESKİ KODDAK delete_product_media FONKSİYONU
    ShopifyAPI sınıfına eklenmesi gereken fonksiyon
    """
    if not media_ids: 
        return
        
    logging.info(f"Ürün GID: {product_id} için {len(media_ids)} medya siliniyor...")
    
    query = """
    mutation productDeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
        productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
            deletedMediaIds
            userErrors { field message }
        }
    }
    """
    try:
        result = shopify_api.execute_graphql(query, {'productId': product_id, 'mediaIds': media_ids})
        deleted_ids = result.get('productDeleteMedia', {}).get('deletedMediaIds', [])
        errors = result.get('productDeleteMedia', {}).get('userErrors', [])
        
        if errors: 
            logging.warning(f"Medya silme hataları: {errors}")
        
        logging.info(f"{len(deleted_ids)} medya başarıyla silindi.")
        
    except Exception as e:
        logging.error(f"Medya silinirken kritik hata oluştu: {e}")


def reorder_product_media(shopify_api, product_id, media_ids):
    """
    ESKİ KODDAK reorder_product_media FONKSİYONU  
    ShopifyAPI sınıfına eklenmesi gereken fonksiyon
    """
    if not media_ids or len(media_ids) < 2:
        logging.info("Yeniden sıralama için yeterli medya bulunmuyor (1 veya daha az).")
        return

    moves = [{"id": media_id, "newPosition": str(i)} for i, media_id in enumerate(media_ids)]
    
    logging.info(f"Ürün {product_id} için {len(moves)} medya yeniden sıralama işlemi gönderiliyor...")
    
    query = """
    mutation productReorderMedia($id: ID!, $moves: [MoveInput!]!) {
      productReorderMedia(id: $id, moves: $moves) {
        userErrors {
          field
          message
        }
      }
    }
    """
    try:
        result = shopify_api.execute_graphql(query, {'id': product_id, 'moves': moves})
        
        errors = result.get('productReorderMedia', {}).get('userErrors', [])
        if errors:
            logging.warning(f"Medya yeniden sıralama hataları: {errors}")
        else:
            logging.info("✅ Medya yeniden sıralama işlemi başarıyla gönderildi.")
            
    except Exception as e:
        logging.error(f"Medya yeniden sıralanırken kritik hata: {e}")


# ShopifyAPI sınıfına eksik fonksiyonları dinamik olarak ekleyen yardımcı
def patch_shopify_api(shopify_api):
    """ShopifyAPI instance'ına eksik fonksiyonları ekler"""
    shopify_api.get_product_media_details = lambda product_gid: get_product_media_details(shopify_api, product_gid)
    shopify_api.delete_product_media = lambda product_id, media_ids: delete_product_media(shopify_api, product_id, media_ids) 
    shopify_api.reorder_product_media = lambda product_id, media_ids: reorder_product_media(shopify_api, product_id, media_ids)