# operations/price_sync.py (Basitleştirilmiş ve Stabil Versiyon)

import logging
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

def send_prices_to_shopify(shopify_api, calculated_df, variants_df, price_column_name, compare_price_column_name=None, progress_callback=None, worker_count=10, max_retries=3):
    """
    Basitleştirilmiş ve hızlı versiyon - Minimum API çağrısı
    """
    start_time = time.time()
    
    if progress_callback: 
        progress_callback({'progress': 5, 'message': 'Veriler hazırlanıyor...'})
    
    # Fiyatları hazırla
    prices_to_apply = calculated_df[['MODEL KODU', price_column_name]]
    if compare_price_column_name and compare_price_column_name in calculated_df.columns:
        prices_to_apply = calculated_df[['MODEL KODU', price_column_name, compare_price_column_name]]
    
    prices_to_apply = prices_to_apply.rename(columns={'MODEL KODU': 'base_sku'})
    df_to_send = pd.merge(variants_df, prices_to_apply, on='base_sku', how='left')
    df_to_send.dropna(subset=[price_column_name], inplace=True)

    if df_to_send.empty:
        return {"success": 0, "failed": 0, "errors": ["Gönderilecek veri bulunamadı."], "details": []}

    total_to_update = len(df_to_send)
    logging.info(f"Toplam {total_to_update} varyant güncellenecek")
    
    if progress_callback: 
        progress_callback({'progress': 10, 'message': f'{total_to_update} varyant için Shopify ID\'leri alınıyor...'})
    
    # SKU listesini al
    skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
    
    # SKU'ları küçük parçalara böl ve eşleştir
    variant_map = {}
    batch_size = 20  # Daha küçük batch = daha hızlı yanıt
    
    for i in range(0, len(skus_to_update), batch_size):
        batch = skus_to_update[i:i+batch_size]
        
        if progress_callback and i % 100 == 0:  # Her 100 SKU'da bir güncelle
            progress = 10 + int((i / len(skus_to_update)) * 15)
            progress_callback({
                'progress': progress, 
                'message': f'ID eşleştirme: {i}/{len(skus_to_update)}...'
            })
        
        try:
            batch_map = shopify_api.get_variant_ids_by_skus(batch)
            variant_map.update(batch_map)
        except Exception as e:
            logging.error(f"Batch hatası (devam ediliyor): {e}")
    
    if not variant_map:
        return {"success": 0, "failed": total_to_update, "errors": ["Hiçbir SKU eşleştirilemedi"], "details": []}
    
    logging.info(f"{len(variant_map)} SKU eşleştirildi")
    
    # Güncellenecek varyantları hazırla
    updates = []
    for _, row in df_to_send.iterrows():
        sku = str(row['MODEL KODU'])
        if sku in variant_map:
            updates.append({
                "id": variant_map[sku],
                "price": f"{row[price_column_name]:.2f}",
                "sku": sku,
                "compareAtPrice": f"{row[compare_price_column_name]:.2f}" if compare_price_column_name and row.get(compare_price_column_name) else None
            })
    
    if not updates:
        return {"success": 0, "failed": total_to_update, "errors": ["Güncellenecek varyant bulunamadı"], "details": []}
    
    logging.info(f"{len(updates)} varyant güncellenecek")
    
    if progress_callback:
        progress_callback({
            'progress': 25,
            'message': f'🚀 {len(updates)} varyant için {worker_count} paralel işlem başlatılıyor...'
        })
    
    # Paralel güncelleme
    results = _parallel_update_simple(shopify_api, updates, progress_callback, worker_count, max_retries)
    
    elapsed = time.time() - start_time
    logging.info(f"İşlem {elapsed:.1f} saniyede tamamlandı")
    
    return results


def _parallel_update_simple(shopify_api, updates, progress_callback, worker_count, max_retries):
    """
    Basit ve güvenilir paralel güncelleme
    """
    total = len(updates)
    results = {
        "success": 0,
        "failed": 0,
        "errors": [],
        "details": []
    }
    
    # Thread-safe sayaçlar
    lock = threading.Lock()
    processed = [0]  # Liste içinde tutarak reference olarak kullan
    
    def update_variant(update_data):
        """Tek varyant güncelle"""
        variant_id = update_data["id"]
        sku = update_data["sku"]
        
        # Numeric ID'yi al
        variant_id_numeric = variant_id.split("/")[-1]
        
        for attempt in range(max_retries):
            try:
                # Kısa rastgele gecikme (rate limit için)
                time.sleep(random.uniform(0.01, 0.1))
                
                # REST API çağrısı
                endpoint = f"variants/{variant_id_numeric}.json"
                variant_data = {
                    "variant": {
                        "id": variant_id_numeric,
                        "price": update_data["price"]
                    }
                }
                
                if update_data.get("compareAtPrice"):
                    variant_data["variant"]["compare_at_price"] = update_data["compareAtPrice"]
                
                response = shopify_api._make_request("PUT", endpoint, data=variant_data)
                
                # Başarılı
                if response and "variant" in response:
                    with lock:
                        processed[0] += 1
                        
                        # Her 100 güncellemede progress göster
                        if processed[0] % 100 == 0 and progress_callback:
                            progress = 25 + int((processed[0] / total) * 70)
                            progress_callback({
                                'progress': progress,
                                'message': f'Güncelleniyor: {processed[0]}/{total}',
                                'log_detail': f"✅ {processed[0]} varyant güncellendi"
                            })
                    
                    return {
                        "status": "success",
                        "sku": sku,
                        "price": update_data["price"]
                    }
                
            except Exception as e:
                error_str = str(e)
                
                # Rate limit hatası - bekle ve tekrar dene
                if "429" in error_str or "throttle" in error_str.lower():
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # 1, 2, 4 saniye bekle
                        continue
                
                # Diğer hatalar için de tekrar dene
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                
                # Son deneme başarısız
                with lock:
                    processed[0] += 1
                
                return {
                    "status": "failed",
                    "sku": sku,
                    "price": update_data["price"],
                    "reason": error_str[:100]
                }
        
        return {
            "status": "failed",
            "sku": sku,
            "price": update_data["price"],
            "reason": "Max retry aşıldı"
        }
    
    # ThreadPoolExecutor ile paralel işle
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # Tüm görevleri başlat
        futures = [executor.submit(update_variant, update) for update in updates]
        
        # Sonuçları topla
        for future in as_completed(futures):
            try:
                result = future.result(timeout=30)
                
                with lock:
                    if result["status"] == "success":
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(result.get("reason", "Unknown"))
                    
                    results["details"].append(result)
                    
            except Exception as e:
                with lock:
                    results["failed"] += 1
                    results["errors"].append(str(e)[:100])
    
    # Final progress
    if progress_callback:
        progress_callback({
            'progress': 100,
            'message': f'✅ Tamamlandı! Başarılı: {results["success"]}, Başarısız: {results["failed"]}'
        })
    
    return results