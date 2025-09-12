# operations/price_sync.py (Tamamen Düzeltilmiş Sürüm)

import logging
import json
import requests
import time
import pandas as pd

def send_prices_to_shopify(shopify_api, calculated_df, variants_df, price_column_name, compare_price_column_name=None, progress_callback=None):
    """
    Hesaplanmış fiyatları (calculated_df) ve tüm varyant listesini (variants_df) alarak
    Shopify'a toplu fiyat güncellemesi gönderir. Tüm hazırlık mantığı bu fonksiyondadır.
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
    variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)

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
    """Her ürün için varyantları productVariantsBulkUpdate ile günceller."""
    
    total_products = len(product_variants_map)
    total_variants = sum(len(variants) for variants in product_variants_map.values())
    success_count = 0
    failed_count = 0
    errors = []
    details = []
    processed_products = 0
    
    for product_id, variants in product_variants_map.items():
        processed_products += 1
        
        if progress_callback:
            progress = int((processed_products / total_products) * 100)
            progress_callback({
                'progress': progress, 
                'message': f'Ürün {processed_products}/{total_products} güncelleniyor...'
            })
        
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
                    if progress_callback:
                        log_msg = f"❌ HATA: Ürün {product_id} varyantları güncellenemedi: {error_msg}"
                        progress_callback({'log_detail': log_msg})
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
                    if progress_callback:
                        log_msg = f"✅ BAŞARILI: Varyant {variant.get('sku')} güncellendi."
                        progress_callback({'log_detail': log_msg})
                logging.info(f"Ürün {product_id} için {len(variants)} varyant başarıyla güncellendi.")
                
        except Exception as e:
            logging.error(f"Ürün {product_id} güncellenirken hata: {e}")
            
            # Bu ürünün varyantlarını REST API ile güncellemeyi dene
            for variant in variants:
                try:
                    variant_id_numeric = variant["id"].split("/")[-1]
                    endpoint = f"variants/{variant_id_numeric}.json"
                    
                    variant_data = {
                        "variant": {
                            "id": variant_id_numeric,
                            "price": variant["price"]
                        }
                    }
                    
                    if "compareAtPrice" in variant:
                        variant_data["variant"]["compare_at_price"] = variant["compareAtPrice"]
                    
                    response = shopify_api._make_request("PUT", endpoint, data=variant_data)
                    
                    if response and "variant" in response:
                        success_count += 1
                        details.append({
                            "status": "success",
                            "variant_id": variant["id"],
                            "sku": variant.get("sku"),
                            "price": variant["price"],
                            "reason": "Başarıyla güncellendi (REST)."
                        })
                        if progress_callback:
                            log_msg = f"✅ BAŞARILI: Varyant {variant.get('sku')} REST API ile güncellendi."
                            progress_callback({'log_detail': log_msg})
                    else:
                        raise Exception("REST API yanıt vermedi")
                        
                except Exception as rest_error:
                    failed_count += 1
                    error_msg = f"GraphQL: {str(e)}, REST: {str(rest_error)}"
                    details.append({
                        "status": "failed",
                        "variant_id": variant["id"],
                        "sku": variant.get("sku"),
                        "price": variant["price"],
                        "reason": error_msg
                    })
                    errors.append(error_msg)
                    if progress_callback:
                        log_msg = f"❌ HATA: Varyant {variant.get('sku')} güncellenemedi: {error_msg}"
                        progress_callback({'log_detail': log_msg})
    
    if progress_callback:
        progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})
    
    logging.info(f"Güncelleme tamamlandı. Başarılı: {success_count}, Başarısız: {failed_count}")
    
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