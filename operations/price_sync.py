# operations/price_sync.py (Düzeltilmiş Sürüm)

import logging
import requests
import time
import random

def update_prices_for_single_product(shopify_api, product_id, variants_to_update, rate_limiter):
    """
    Tek bir ürüne ait varyantların fiyatlarını REST API ile tek tek günceller.
    Paylaşılan bir rate_limiter objesi kullanarak hız limitlerini aşmaz.
    """
    if not variants_to_update:
        return {"status": "skipped", "reason": "Güncellenecek varyant yok."}

    success_count = 0
    errors = []
    max_retries = 3

    for variant_payload in variants_to_update:
        variant_gid = variant_payload.get("id")
        variant_id_numeric = variant_gid.split("/")[-1]
        
        for attempt in range(max_retries):
            try:
                # İstek göndermeden önce hız limitini bekle
                rate_limiter.wait()

                endpoint = f"variants/{variant_id_numeric}.json"
                
                # REST API için doğru payload formatı
                data_to_send = {"variant": {"id": int(variant_id_numeric), "price": variant_payload["price"]}}
                if "compareAtPrice" in variant_payload:
                    data_to_send["variant"]["compare_at_price"] = variant_payload["compareAtPrice"]

                # _make_request'e dictionary olarak gönderiyoruz, o JSON'a çeviriyor
                shopify_api._make_request("PUT", endpoint, data=data_to_send)
                
                success_count += 1
                logging.info(f"✅ Varyant {variant_id_numeric} başarıyla güncellendi: {variant_payload['price']}")
                break # Başarılı oldu, bir sonraki varyanta geç

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logging.warning(f"Rate limit! {variant_id_numeric} için {wait_time:.1f}s bekleniyor...")
                    time.sleep(wait_time)
                else:
                    error_msg = f"Varyant {variant_id_numeric} güncellenemedi: {e}"
                    logging.error(error_msg)
                    errors.append(error_msg)
                    break # Hata kalıcı, bir sonraki varyanta geç
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    error_msg = f"Varyant {variant_id_numeric} güncellenemedi (Genel Hata): {e}"
                    logging.error(error_msg)
                    errors.append(error_msg)
                    break

    if errors:
        return {"status": "failed", "reason": "; ".join(errors)}
    else:
        logging.info(f"✅ Ürün {product_id.split('/')[-1]} için {success_count} varyant başarıyla güncellendi.")
        return {"status": "success", "updated_count": success_count}


def _process_one_product_for_price_sync(shopify_api, product_base_sku, all_variants_df, price_data_df, price_col, compare_col, rate_limiter):
    """
    DÜZELTME: Tek bir ürünü baştan sona işleyen worker fonksiyonu.
    Varyant eşleştirme mantığı tamamen düzeltildi.
    """
    try:
        # 1. Önce bu ürüne ait tüm varyant SKU'larını bulalım
        product_variants = all_variants_df[all_variants_df['base_sku'] == product_base_sku]
        if product_variants.empty:
            return {"status": "failed", "reason": f"Varyant listesinde ürün bulunamadı: {product_base_sku}"}
        
        variant_skus = product_variants['MODEL KODU'].tolist()
        logging.info(f"Ürün {product_base_sku} için {len(variant_skus)} varyant bulundu: {variant_skus}")
        
        # 2. Bu varyant SKU'ları için Shopify'dan ID'leri alalım
        variant_map = shopify_api.get_variant_ids_by_skus(variant_skus, search_by_product_sku=False)
        if not variant_map:
            return {"status": "failed", "reason": f"Shopify'da varyantlar bulunamadı: {variant_skus}"}

        # 3. Ana ürünün hesaplanmış fiyatını bul
        price_row = price_data_df.loc[price_data_df['MODEL KODU'] == product_base_sku]
        if price_row.empty:
            return {"status": "skipped", "reason": f"Hesaplanmış fiyat listesinde ürün bulunamadı: {product_base_sku}"}
        
        price_to_set = price_row.iloc[0][price_col]
        compare_price_to_set = price_row.iloc[0].get(compare_col)

        # 4. Her varyant için güncelleme verisini hazırla
        updates = []
        for variant_sku in variant_skus:
            if variant_sku in variant_map:
                variant_info = variant_map[variant_sku]
                payload = {
                    "id": variant_info['variant_id'], 
                    "price": f"{price_to_set:.2f}",
                    "sku": variant_sku  # Debug için ekliyoruz
                }
                if compare_price_to_set is not None and pd.notna(compare_price_to_set):
                    payload["compareAtPrice"] = f"{compare_price_to_set:.2f}"
                updates.append(payload)
                logging.info(f"Varyant {variant_sku} için fiyat güncelleme hazırlandı: {price_to_set:.2f}")
            else:
                logging.warning(f"Varyant SKU {variant_sku} Shopify'da bulunamadı")

        if not updates:
            return {"status": "skipped", "reason": "Shopify'da eşleşen varyant bulunamadı."}

        # 5. Product ID'yi ilk varyanttan alalım
        first_variant_info = list(variant_map.values())[0]
        product_id = first_variant_info['product_id']

        # 6. REST tabanlı güncelleme fonksiyonunu çağır
        result = update_prices_for_single_product(shopify_api, product_id, updates, rate_limiter)
        
        # Sonucu detaylandır
        if result.get('status') == 'success':
            rate_limiter.on_success()  # Başarı durumunda hızlan
        elif "throttled" in result.get('reason', '').lower():
            rate_limiter.on_throttle()  # Throttle durumunda yavaşla
            
        return result
    except Exception as e:
        if "throttled" in str(e).lower():
            rate_limiter.on_throttle()
        return {"status": "failed", "reason": str(e)}