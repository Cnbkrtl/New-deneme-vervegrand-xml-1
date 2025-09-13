# operations/price_sync.py (Tamamen Düzeltilmiş Sürüm)

import logging
import json
import requests
import time
import pandas as pd

def send_prices_to_shopify(shopify_api, calculated_df, variants_df, price_column_name, compare_price_column_name=None, progress_callback=None):
    """
    Hesaplanmış fiyatları (calculated_df) ve tüm varyant listesini (variants_df) alarak
    Shopify'a toplu fiyat güncellemesi gönderir. 
    """
    if progress_callback: 
        progress_callback({'progress': 5, 'message': 'Fiyatlar ve varyantlar birleştiriliyor...'})
    
    prices_to_apply = calculated_df[['MODEL KODU', price_column_name]]
    if compare_price_column_name and compare_price_column_name in calculated_df.columns:
        prices_to_apply = calculated_df[['MODEL KODU', price_column_name, compare_price_column_name]]
    
    prices_to_apply = prices_to_apply.rename(columns={'MODEL KODU': 'base_sku'})
    df_to_send = pd.merge(variants_df, prices_to_apply, on='base_sku', how='left')
    df_to_send.dropna(subset=[price_column_name], inplace=True)

    if df_to_send.empty:
        logging.warning("Shopify'a gönderilecek güncel fiyatlı ürün bulunamadı.")
        return {"success": 0, "failed": 0, "errors": ["Gönderilecek veri bulunamadı."], "details": []}

    if progress_callback: 
        progress_callback({'progress': 15, 'message': 'Varyantlar Shopify ile eşleştiriliyor...'})
    
    skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
    
    # Daha hızlı eşleştirme için batch işlem
    variant_map = {}
    for i in range(0, len(skus_to_update), 50):
        batch = skus_to_update[i:i+50]
        if progress_callback:
            progress = 15 + int((i / len(skus_to_update)) * 10)
            progress_callback({'progress': progress, 'message': f'SKU eşleştirme: {i}/{len(skus_to_update)}...'})
        
        try:
            batch_map = shopify_api.get_variant_ids_by_skus(batch)
            variant_map.update(batch_map)
        except Exception as e:
            logging.error(f"SKU batch {i//50 + 1} eşleştirilemedi: {e}")
    
    # Güncellenecek varyantları hazırla
    updates = []
    for _, row in df_to_send.iterrows():
        sku = str(row['MODEL KODU'])
        if sku in variant_map:
            payload = {
                "id": variant_map[sku], 
                "price": f"{row[price_column_name]:.2f}", 
                "sku": sku
            }
            if compare_price_column_name and row.get(compare_price_column_name) is not None:
                payload["compareAtPrice"] = f"{row[compare_price_column_name]:.2f}"
            updates.append(payload)
    
    if not updates:
        logging.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")
        return {"success": 0, "failed": len(skus_to_update), "errors": ["Shopify'da eşleşen SKU bulunamadı."], "details": []}

    logging.info(f"{len(updates)} adet varyant fiyat güncellemesi başlatılıyor.")
    
    # Doğrudan REST API kullan - daha basit ve güvenilir
    return _update_prices_individually(shopify_api, updates, progress_callback)

    # Varyantları product'a göre grupla
    product_variants_map = {}
    skipped_count = 0
    
    for _, row in df_to_send.iterrows():
        sku = str(row['MODEL KODU'])
        if sku in variant_map:
            variant_id = variant_map[sku]
            
            # Product ID'yi bulmak için varyantı sorgula
            query = """
            query getProductIdFromVariant($id: ID!) {
                productVariant(id: $id) {
                    product { id }
                }
            }
            """
            
            try:
                result = shopify_api.execute_graphql(query, {"id": variant_id})
                product_id = result.get("productVariant", {}).get("product", {}).get("id")
                
                if product_id:
                    if product_id not in product_variants_map:
                        product_variants_map[product_id] = []
                    
                    variant_update = {
                        "id": variant_id,
                        "price": f"{row[price_column_name]:.2f}",
                        "sku": sku
                    }
                    
                    if compare_price_column_name and row.get(compare_price_column_name) is not None:
                        variant_update["compareAtPrice"] = f"{row[compare_price_column_name]:.2f}"
                    
                    product_variants_map[product_id].append(variant_update)
                else:
                    logging.warning(f"SKU {sku} için product ID bulunamadı.")
                    skipped_count += 1
            except Exception as e:
                logging.error(f"SKU {sku} için product ID alınırken hata: {e}")
                skipped_count += 1
        else:
            logging.warning(f"SKU {sku} için Shopify'da eşleşen varyant bulunamadı.")
            skipped_count += 1
    
    if not product_variants_map:
        logging.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")
        return {"success": 0, "failed": len(skus_to_update), "errors": ["Shopify'da eşleşen SKU bulunamadı."], "details": []}

    total_variants = sum(len(variants) for variants in product_variants_map.values())
    logging.info(f"{total_variants} adet varyant, {len(product_variants_map)} ürün için güncelleme başlatılıyor.")
    
    # Ürün bazında güncelleme yap
    return _update_variants_by_product(shopify_api, product_variants_map, progress_callback)


def _update_variants_by_product(shopify_api, product_variants_map, progress_callback=None):
    """Her ürün için varyantları productVariantsBulkUpdate ile günceller - hızlı yöntem."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    total_products = len(product_variants_map)
    total_variants = sum(len(variants) for variants in product_variants_map.values())
    details = []
    errors = []
    
    # Thread-safe sayaçlar
    counter_lock = threading.Lock()
    processed_products = 0
    success_count = 0
    failed_count = 0
    
    def update_product_variants(product_id, variants):
        nonlocal processed_products, success_count, failed_count
        
        try:
            # productVariantsBulkUpdate mutation'ı
            mutation = """
            mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                    productVariants {
                        id
                        price
                        compareAtPrice
                    }
                    userErrors {
                        field
                        message
                    }
                }
            }
            """
            
            # Varyant input'larını hazırla
            variant_inputs = []
            for variant in variants:
                variant_input = {
                    "id": variant["id"],
                    "price": variant["price"]
                }
                if "compareAtPrice" in variant:
                    variant_input["compareAtPrice"] = variant["compareAtPrice"]
                variant_inputs.append(variant_input)
            
            # Mutation'ı çalıştır
            result = shopify_api.execute_graphql(mutation, {
                "productId": product_id,
                "variants": variant_inputs
            })
            
            with counter_lock:
                processed_products += 1
                
                if user_errors := result.get("productVariantsBulkUpdate", {}).get("userErrors"):
                    # Hata varsa
                    for variant in variants:
                        failed_count += 1
                        error_msg = ", ".join([f"{err.get('field', '')}: {err.get('message', '')}" for err in user_errors])
                        details.append({
                            "status": "failed",
                            "variant_id": variant["id"],
                            "sku": variant.get("sku"),
                            "price": variant["price"],
                            "reason": error_msg
                        })
                    errors.extend([err.get('message', 'Bilinmeyen hata') for err in user_errors])
                else:
                    # Başarılı
                    for variant in variants:
                        success_count += 1
                        details.append({
                            "status": "success",
                            "variant_id": variant["id"],
                            "sku": variant.get("sku"),
                            "price": variant["price"],
                            "reason": "Başarıyla güncellendi."
                        })
                    
                if progress_callback and processed_products % 10 == 0:
                    progress = int((processed_products / total_products) * 100)
                    progress_callback({
                        'progress': progress,
                        'message': f'Ürünler güncelleniyor: {processed_products}/{total_products} (✅ {success_count} / ❌ {failed_count} varyant)'
                    })
                    
        except Exception as e:
            with counter_lock:
                processed_products += 1
                for variant in variants:
                    failed_count += 1
                    details.append({
                        "status": "failed",
                        "variant_id": variant["id"],
                        "sku": variant.get("sku"),
                        "price": variant["price"],
                        "reason": str(e)
                    })
                errors.append(str(e))
    
    # GraphQL mutation'ları için 5 worker yeterli (REST'ten daha hızlı)
    max_workers = min(5, total_products)
    
    logging.info(f"🚀 {total_products} ürün için {max_workers} worker ile GraphQL güncelleme başlatılıyor...")
    
    if progress_callback:
        progress_callback({
            'progress': 5,
            'message': f'🚀 {total_products} ürün için hızlı güncelleme başlatılıyor...'
        })
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(update_product_variants, product_id, variants)
            for product_id, variants in product_variants_map.items()
        ]
        
        for future in as_completed(futures):
            try:
                future.result(timeout=60)
            except Exception as e:
                logging.error(f"Worker hatası: {e}")
    
    if progress_callback:
        progress_callback({
            'progress': 100,
            'message': f'✅ Tamamlandı! Başarılı: {success_count}, Başarısız: {failed_count}'
        })
    
    logging.info(f"🎉 GraphQL güncelleme tamamlandı. Başarılı: {success_count}, Başarısız: {failed_count}")
    
    return {
        "success": success_count,
        "failed": failed_count,
        "errors": errors,
        "details": details
    }


def _update_prices_individually(shopify_api, price_updates: list, progress_callback=None):
    """Fiyatları tek tek REST API ile günceller (fallback metodu)."""
    success_count, failed_count, errors, total = 0, 0, [], len(price_updates)
    details = []
    
    for i, update in enumerate(price_updates):
        log_message = f"Varyant {i+1}/{total} ({update.get('sku')}): Fiyat {update.get('price')} olarak güncelleniyor..."
        if progress_callback:
            progress = int((i / total) * 100)
            progress_callback({
                'progress': progress, 
                'message': f'Tek tek güncelleniyor: {i+1}/{total}', 
                'log_detail': log_message
            })
        
        variant_gid = update.get("id") or update.get("variant_id")
        
        try:
            # REST API üzerinden güncelleme
            variant_id_numeric = variant_gid.split("/")[-1]
            endpoint = f"variants/{variant_id_numeric}.json"
            
            variant_data = {
                "variant": {
                    "id": variant_id_numeric,
                    "price": str(update.get("price"))
                }
            }
            
            if "compareAtPrice" in update and update["compareAtPrice"] is not None:
                variant_data["variant"]["compare_at_price"] = str(update["compareAtPrice"])
            
            response = shopify_api._make_request("PUT", endpoint, data=variant_data)
            
            if response and "variant" in response:
                success_count += 1
                log_message = f"✅ BAŞARILI: Varyant {update.get('sku')} için fiyat başarıyla güncellendi (REST API)."
                details.append({
                    "status": "success",
                    "variant_id": variant_gid,
                    "sku": update.get("sku"),
                    "price": update.get("price"),
                    "reason": "Başarıyla güncellendi (REST)."
                })
                if progress_callback:
                    progress_callback({'log_detail': log_message})
                logging.info(log_message)
            else:
                failed_count += 1
                error_message = "REST API yanıt vermedi veya bilinmeyen hata oluştu."
                log_message = f"❌ HATA: Varyant {update.get('sku')} için fiyat güncellenemedi. Neden: {error_message}"
                details.append({
                    "status": "failed",
                    "variant_id": variant_gid,
                    "sku": update.get("sku"),
                    "price": update.get("price"),
                    "reason": error_message
                })
                if progress_callback:
                    progress_callback({'log_detail': log_message})
                logging.error(log_message)
                
        except Exception as e:
            failed_count += 1
            log_message = f"❌ KRİTİK HATA: Varyant {update.get('sku')} REST API sorgusu başarısız oldu. Hata: {e}"
            errors.append(str(e))
            details.append({
                "status": "failed",
                "variant_id": variant_gid,
                "sku": update.get("sku"),
                "price": update.get("price"),
                "reason": str(e)
            })
            if progress_callback:
                progress_callback({'log_detail': log_message})
            logging.error(log_message)
    
    if progress_callback:
        progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})
    
    return {"success": success_count, "failed": failed_count, "errors": errors, "details": details}