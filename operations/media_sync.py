# operations/media_sync.py

import logging
import time

def sync_media(shopify_api, sentos_api, product_gid, sentos_product, set_alt_text=False):
    """Bir ürünün medya dosyalarını senkronize eder."""
    changes = []
    product_title = sentos_product.get('name', '').strip()
    sentos_ordered_urls = sentos_api.get_ordered_image_urls(sentos_product.get('id'))
    
    if sentos_ordered_urls is None:
         changes.append("Medya senkronizasyonu atlandı (Cookie eksik).")
         return changes
    
    initial_shopify_media = shopify_api.get_product_media_details(product_gid)
    
    if not sentos_ordered_urls:
        if media_ids_to_delete := [m['id'] for m in initial_shopify_media]:
            _delete_media(shopify_api, product_gid, media_ids_to_delete)
            changes.append(f"{len(media_ids_to_delete)} Shopify görseli silindi.")
        return changes
        
    shopify_src_map = {m['originalSrc']: m for m in initial_shopify_media if m.get('originalSrc')}
    media_ids_to_delete = [media['id'] for src, media in shopify_src_map.items() if src not in sentos_ordered_urls]
    urls_to_add = [url for url in sentos_ordered_urls if url not in shopify_src_map]
    
    media_changed = False
    if urls_to_add:
        changes.append(f"{len(urls_to_add)} yeni görsel eklendi.")
        _add_media(shopify_api, product_gid, urls_to_add, product_title, set_alt_text)
        media_changed = True
        
    if media_ids_to_delete:
        changes.append(f"{len(media_ids_to_delete)} eski görsel silindi.")
        _delete_media(shopify_api, product_gid, media_ids_to_delete)
        media_changed = True
        
    if media_changed:
        changes.append("Görsel sırası güncellendi.")
        time.sleep(10) # Medyanın işlenmesi için bekle
        
        final_shopify_media = shopify_api.get_product_media_details(product_gid)
        final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
        ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]
        _reorder_media(shopify_api, product_gid, ordered_media_ids)
    
    if not changes and not media_changed:
        changes.append("Resimler kontrol edildi (Değişiklik yok).")
        
    return changes

def _add_media(shopify_api, product_gid, urls, product_title, set_alt_text):
    media_input = [{"originalSource": url, "alt": product_title if set_alt_text else url, "mediaContentType": "IMAGE"} for url in urls]
    for i in range(0, len(media_input), 10): # 10'lu gruplar halinde ekle
        batch = media_input[i:i + 10]
        try:
            query = "mutation productCreateMedia($pId: ID!, $media: [CreateMediaInput!]!) { productCreateMedia(productId: $pId, media: $media) { media { id } mediaUserErrors { field message } } }"
            shopify_api.execute_graphql(query, {'pId': product_gid, 'media': batch})
        except Exception as e:
            logging.error(f"Medya batch {i//10 + 1} eklenirken hata: {e}")

def _delete_media(shopify_api, product_id, media_ids):
    if not media_ids: return
    query = "mutation pDM($pId: ID!, $mIds: [ID!]!) { productDeleteMedia(productId: $pId, mediaIds: $mIds) { deletedMediaIds userErrors { field message } } }"
    try:
        shopify_api.execute_graphql(query, {'pId': product_id, 'mIds': media_ids})
    except Exception as e:
        logging.error(f"Medya silinirken hata: {e}")

def _reorder_media(shopify_api, product_id, media_ids):
    if not media_ids or len(media_ids) < 2: return
    moves = [{"id": media_id, "newPosition": str(i)} for i, media_id in enumerate(media_ids)]
    query = "mutation pRM($id: ID!, $moves: [MoveInput!]!) { productReorderMedia(id: $id, moves: $moves) { userErrors { field message } } }"
    try:
        shopify_api.execute_graphql(query, {'id': product_id, 'moves': moves})
    except Exception as e:
        logging.error(f"Medya yeniden sıralanırken hata: {e}")