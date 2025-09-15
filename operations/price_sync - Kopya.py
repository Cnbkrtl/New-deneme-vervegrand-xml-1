# operations/price_sync.py (Optimize Edilmiş Versiyon)

import logging
import json
import requests
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

def send_prices_to_shopify(shopify_api, calculated_df, variants_df, price_column_name, compare_price_column_name=None, progress_callback=None, worker_count=10, max_retries=3):
    """
    Hesaplanmış fiyatları (calculated_df) ve tüm varyant listesini (variants_df) alarak
    Shopify'a toplu fiyat güncellemesi gönderir. 
    Önce ana ürün SKU'su ile eşleştirme dener, bu daha sağlamdır.
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
        progress_callback({'progress': 15, 'message': 'Varyantlar Shopify ile eşleştiriliyor (Ürün Bazlı Arama)...'})
    
    # YENİ STRATEJİ: Doğrudan varyant SKU'su yerine, ana ürünlerin SKU'larını (base_sku) al
    base_skus_to_search = df_to_send['base_sku'].dropna().astype(str).unique().tolist()
    logging.info(f"{len(base_skus_to_search)} adet ana ürün (base_sku) üzerinden Shopify'da arama yapılacak...")

    try:
        # Önce ana ürünleri arayarak o ürünlere ait TÜM varyantları çek. Bu yöntem daha güvenilirdir.
        variant_map = shopify_api.get_variant_ids_by_skus(base_skus_to_search, search_by_product_sku=True)
        logging.info(f"Ürün bazlı arama sonucu {len(variant_map)} adet varyant Shopify'da bulundu.")
    except Exception as e:
        logging.error(f"Ana ürün bazlı SKU eşleştirmesi sırasında kritik hata: {e}. İşlem durduruldu.")
        return {"success": 0, "failed": len(df_to_send), "errors": [f"SKU eşleştirme hatası: {e}"], "details": []}
    
    # Güncellenecek varyantları hazırla
    updates = []
    skipped_skus = []
    
    # df_to_send'deki her satır için (yani her bir varyant için) eşleşme ara
    for _, row in df_to_send.iterrows():
        # Güncellenecek olan, varyantın kendi SKU'su ('MODEL KODU')
        variant_sku_to_update = str(row['MODEL KODU'])
        
        # variant_map içinde bu SKU'ya karşılık gelen bir ID var mı?
        if variant_sku_to_update in variant_map:
            payload = {
                "id": variant_map[variant_sku_to_update], 
                "price": f"{row[price_column_name]:.2f}", 
                "sku": variant_sku_to_update
            }
            if compare_price_column_name and row.get(compare_price_column_name) is not None:
                payload["compareAtPrice"] = f"{row[compare_price_column_name]:.2f}"
            updates.append(payload)
        else:
            skipped_skus.append(variant_sku_to_update)
    
    if skipped_skus:
        logging.warning(f"{len(skipped_skus)} varyant SKU'su, ana ürünleri bulunmasına rağmen Shopify'da eşleştirilemedi. İlk 10: {skipped_skus[:10]}")
    
    if not updates:
        logging.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")
        return {"success": 0, "failed": len(df_to_send), "errors": ["Shopify'da eşleşen SKU bulunamadı."], "details": []}

    logging.info(f"{len(updates)} adet varyant için güncelleme başlatılıyor...")
    
    if worker_count > 1:
        return _update_prices_parallel(shopify_api, updates, progress_callback, worker_count, max_retries)
    else:
        return _update_prices_sequentially(shopify_api, updates, progress_callback, max_retries)


def _update_prices_parallel(shopify_api, price_updates: list, progress_callback=None, worker_count=10, max_retries=3):
    """Fiyatları paralel olarak REST API ile günceller - Rate limit korumalı!"""
    total = len(price_updates)
    details = []
    errors = []
    
    # Thread-safe sayaçlar ve rate limit kontrolü
    counter_lock = threading.Lock()
    processed_count = 0
    success_count = 0
    failed_count = 0
    rate_limit_hits = 0
    start_time = time.time()
    
    def update_single_variant_with_retry(update_data):
        """Tek bir varyantı günceller, gerekirse tekrar dener"""
        nonlocal processed_count, success_count, failed_count, rate_limit_hits
        
        variant_gid = update_data.get("id")
        sku = update_data.get("sku", "Unknown")
        
        for attempt in range(max_retries):
            try:
                # Rate limiting için kısa bekleme
                time.sleep(random.uniform(0.05, 0.15))  # 50-150ms rastgele bekleme
                
                # REST API üzerinden güncelleme
                variant_id_numeric = variant_gid.split("/")[-1]
                endpoint = f"variants/{variant_id_numeric}.json"
                
                variant_data = {
                    "variant": {
                        "id": variant_id_numeric,
                        "price": str(update_data.get("price"))
                    }
                }
                
                if "compareAtPrice" in update_data:
                    variant_data["variant"]["compare_at_price"] = str(update_data["compareAtPrice"])
                
                # ShopifyAPI içindeki _make_request metodunu kullanarak daha sağlam bir çağrı
                response = shopify_api._make_request("PUT", endpoint, data=variant_data)
                
                with counter_lock:
                    processed_count += 1
                    
                    if response and "variant" in response:
                        success_count += 1
                        
                        # Progress update
                        if progress_callback and processed_count % 50 == 0:
                            elapsed = time.time() - start_time
                            rate = processed_count / elapsed if elapsed > 0 else 0
                            eta = (total - processed_count) / rate if rate > 0 else 0
                            progress = 25 + int((processed_count / total) * 70)  # 25-95% arası
                            
                            progress_callback({
                                'progress': progress,
                                'message': f'⚡ Güncelleme: {processed_count}/{total} (✅ {success_count} / ❌ {failed_count}) - {rate:.1f}/s',
                                'log_detail': f"<div style='color:#4CAF50'>✅ {processed_count}/{total} işlendi - Hız: {rate:.1f} varyant/saniye - Tahmini: {eta/60:.1f} dk</div>",
                                'stats': {'rate': rate, 'eta': eta / 60}
                            })
                        
                        return {
                            "status": "success",
                            "variant_id": variant_gid,
                            "sku": sku,
                            "price": update_data.get("price"),
                            "reason": "Başarıyla güncellendi."
                        }
                    else:
                        raise Exception("API yanıt vermedi")
                        
            except requests.exceptions.HTTPError as e:
                error_str = str(e)
                
                # 429 (Too Many Requests) hatasını yakala
                if e.response.status_code == 429:
                    with counter_lock:
                        rate_limit_hits += 1
                    
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 2)  # Üstel geri çekilme
                        logging.warning(f"Rate limit! SKU {sku} için {wait_time:.1f}s bekleniyor... (Deneme {attempt+1})")
                        time.sleep(wait_time)
                        continue
                
                # Diğer HTTP hataları veya son deneme
                if attempt == max_retries - 1:
                    with counter_lock:
                        failed_count += 1
                        if processed_count % 50 == 0 and progress_callback:
                            progress_callback({
                                'log_detail': f"<div style='color:#f44336'>❌ Hata: SKU {sku} - {error_str[:50]}</div>"
                            })
                    
                    return {
                        "status": "failed",
                        "variant_id": variant_gid,
                        "sku": sku,
                        "price": update_data.get("price"),
                        "reason": f"Hata: {error_str[:100]}"
                    }
                
                # Tekrar dene
                time.sleep(1)

            except Exception as e:
                # Diğer tüm hatalar
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                
                with counter_lock:
                    failed_count += 1
                    if processed_count % 50 == 0 and progress_callback:
                        progress_callback({
                            'log_detail': f"<div style='color:#f44336'>❌ Hata: SKU {sku} - {str(e)[:50]}</div>"
                        })
                
                return {
                    "status": "failed",
                    "variant_id": variant_gid,
                    "sku": sku,
                    "price": update_data.get("price"),
                    "reason": f"Hata: {str(e)[:100]}"
                }
    
    logging.info(f"🚀 {total} varyant için {worker_count} worker ile paralel güncelleme başlatılıyor...")
    
    if progress_callback:
        progress_callback({
            'progress': 25,
            'message': f'🚀 {worker_count} paralel işlem başlatılıyor...'
        })
    
    # ThreadPoolExecutor ile paralel işlem
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # Görevleri başlat
        futures = []
        for i, update in enumerate(price_updates):
            # İlk worker'ları yavaş başlat
            if i < worker_count * 2:
                time.sleep(0.05)
            future = executor.submit(update_single_variant_with_retry, update)
            futures.append((future, update))
        
        # Sonuçları topla
        for future, update in futures:
            try:
                result = future.result(timeout=30)
                details.append(result)
                if result["status"] == "failed":
                    errors.append(result["reason"])
            except Exception as e:
                logging.error(f"Worker hatası - SKU {update.get('sku')}: {e}")
                details.append({
                    "status": "failed",
                    "variant_id": update.get("id"),
                    "sku": update.get("sku"),
                    "price": update.get("price"),
                    "reason": f"Worker timeout: {str(e)[:50]}"
                })
                with counter_lock:
                    failed_count += 1
    
    # Final update
    elapsed = time.time() - start_time
    if progress_callback:
        progress_callback({
            'progress': 100,
            'message': f'✅ Tamamlandı! Başarılı: {success_count}, Başarısız: {failed_count} ({elapsed:.1f} saniye)',
            'log_detail': f"<div style='color:#4CAF50;font-weight:bold'>🎉 İşlem tamamlandı! Süre: {elapsed:.1f}s, Ortalama hız: {total/elapsed:.1f} varyant/saniye</div>"
        })
    
    logging.info(f"🎉 Paralel güncelleme tamamlandı. Süre: {elapsed:.1f}s, Başarılı: {success_count}, Başarısız: {failed_count}")
    
    return {
        "success": success_count,
        "failed": failed_count,
        "errors": errors,
        "details": details
    }


def _update_prices_sequentially(shopify_api, price_updates: list, progress_callback=None, max_retries=3):
    """Fiyatları sırayla günceller (tek worker için)"""
    success_count = 0
    failed_count = 0
    errors = []
    details = []
    total = len(price_updates)
    
    for i, update in enumerate(price_updates):
        if progress_callback and i % 25 == 0:
            progress = 25 + int((i / total) * 70)
            progress_callback({
                'progress': progress,
                'message': f'Güncelleniyor: {i}/{total} (✅ {success_count} / ❌ {failed_count})'
            })
        
        variant_gid = update.get("id")
        sku = update.get("sku", "Unknown")
        
        for attempt in range(max_retries):
            try:
                variant_id_numeric = variant_gid.split("/")[-1]
                endpoint = f"variants/{variant_id_numeric}.json"
                
                variant_data = {
                    "variant": {
                        "id": variant_id_numeric,
                        "price": str(update.get("price"))
                    }
                }
                
                if "compareAtPrice" in update:
                    variant_data["variant"]["compare_at_price"] = str(update["compareAtPrice"])
                
                response = shopify_api._make_request("PUT", endpoint, data=variant_data)
                
                if response and "variant" in response:
                    success_count += 1
                    details.append({
                        "status": "success",
                        "variant_id": variant_gid,
                        "sku": sku,
                        "price": update.get("price"),
                        "reason": "Başarıyla güncellendi."
                    })
                    break
                else:
                    raise Exception("API yanıt vermedi")
                    
            except requests.exceptions.HTTPError as e:
                # 429 (Too Many Requests) hatasını yakala
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        time.sleep((2 ** attempt) + random.uniform(0, 2))
                        continue
                
                # Diğer HTTP hataları veya son deneme
                if attempt == max_retries - 1:
                    failed_count += 1
                    error_msg = str(e)[:100]
                    errors.append(error_msg)
                    details.append({
                        "status": "failed",
                        "variant_id": variant_gid,
                        "sku": sku,
                        "price": update.get("price"),
                        "reason": error_msg
                    })
                break

            except Exception as e:
                # Diğer tüm hatalar
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

                failed_count += 1
                error_msg = str(e)[:100]
                errors.append(error_msg)
                details.append({
                    "status": "failed",
                    "variant_id": variant_gid,
                    "sku": sku,
                    "price": update.get("price"),
                    "reason": error_msg
                })
                break
    
    if progress_callback:
        progress_callback({
            'progress': 100,
            'message': f'✅ Tamamlandı! Başarılı: {success_count}, Başarısız: {failed_count}'
        })
    
    return {
        "success": success_count,
        "failed": failed_count,
        "errors": errors,
        "details": details
    }