# operations/price_sync.py (Hatalar Giderilmiş Sürüm)

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
    if progress_callback: progress_callback({'progress': 5, 'message': 'Fiyatlar ve varyantlar birleştiriliyor...'})
    
    prices_to_apply = calculated_df[['MODEL KODU', price_column_name]]
    if compare_price_column_name and compare_price_column_name in calculated_df.columns:
        prices_to_apply = calculated_df[['MODEL KODU', price_column_name, compare_price_column_name]]
    
    prices_to_apply = prices_to_apply.rename(columns={'MODEL KODU': 'base_sku'})
    df_to_send = pd.merge(variants_df, prices_to_apply, on='base_sku', how='left')
    df_to_send.dropna(subset=[price_column_name], inplace=True)

    if df_to_send.empty:
        logging.warning("Shopify'a gönderilecek güncel fiyatlı ürün bulunamadı.")
        return {"success": 0, "failed": 0, "errors": ["Gönderilecek veri bulunamadı."]}

    if progress_callback: progress_callback({'progress': 15, 'message': 'Varyantlar Shopify ile eşleştiriliyor...'})
    skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
    variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)

    updates = []
    for _, row in df_to_send.iterrows():
        sku = str(row['MODEL KODU'])
        if sku in variant_map:
            payload = {"variant_id": variant_map[sku], "price": f"{row[price_column_name]:.2f}"}
            if compare_price_column_name and row.get(compare_price_column_name) is not None:
                payload["compare_at_price"] = f"{row[compare_price_column_name]:.2f}"
            updates.append(payload)
    
    if not updates:
        logging.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")
        return {"success": 0, "failed": len(skus_to_update), "errors": ["Shopify'da eşleşen SKU bulunamadı."]}

    logging.info(f"{len(updates)} adet varyant fiyat güncellemesi için toplu işlem başlatılıyor.")
    return _update_variant_prices_in_bulk(shopify_api, updates, progress_callback)


def _update_variant_prices_in_bulk(shopify_api, price_updates: list, progress_callback=None):
    total_updates = len(price_updates)
    
    try:
        if total_updates <= 50:
            return _update_prices_individually(shopify_api, price_updates, progress_callback)

        if progress_callback: progress_callback({'progress': 20, 'message': f'{total_updates} varyant için güncelleme dosyası hazırlanıyor...'})
        
        jsonl_data = ""
        for update in price_updates:
            price_input = {"id": update["variant_id"], "price": update["price"]}
            if "compare_at_price" in update and update["compare_at_price"] is not None:
                price_input["compareAtPrice"] = update["compare_at_price"]
            jsonl_data += json.dumps({"input": price_input}) + "\n"
        jsonl_bytes = jsonl_data.encode('utf-8')

        if progress_callback: progress_callback({'progress': 30, 'message': 'Shopify yükleme alanı hazırlanıyor...'})
        
        upload_mutation = "mutation stagedUploadsCreate($input: [StagedUploadInput!]!) { stagedUploadsCreate(input: $input) { stagedTargets { url resourceUrl parameters { name value } } userErrors { field message } } }"
        upload_vars = { "input": [{ "resource": "BULK_MUTATION_VARIABLES", "filename": "price_updates.jsonl", "mimeType": "application/jsonl", "httpMethod": "POST" }] }
        upload_result = shopify_api.execute_graphql(upload_mutation, upload_vars)
        
        staged_data = upload_result.get("stagedUploadsCreate")
        if not staged_data or not staged_data.get("stagedTargets"):
            user_errors = staged_data.get("userErrors", []) if staged_data else "stagedUploadsCreate mutation'ı null (boş) sonuç döndürdü."
            raise Exception(f"Staged upload URL'i alınamadı: {user_errors}")

        target = staged_data["stagedTargets"][0]
        
        if progress_callback: progress_callback({'progress': 40, 'message': 'Veriler Shopify\'a yükleniyor...'})
        
        form_data = {param['name']: param['value'] for param in target['parameters']}
        files = {'file': ('price_updates.jsonl', jsonl_bytes, 'application/jsonl')}
        upload_response = requests.post(target['url'], data=form_data, files=files, timeout=90)
        upload_response.raise_for_status()

        if progress_callback: progress_callback({'progress': 55, 'message': 'Toplu güncelleme işlemi başlatılıyor...'})
        
        bulk_mutation = f"""mutation {{ bulkOperationRunMutation( mutation: "mutation call($input: ProductVariantInput!) {{ productVariantUpdate(input: $input) {{ productVariant {{ id }} userErrors {{ field message }} }} }}", stagedUploadPath: "{target['resourceUrl']}" ) {{ bulkOperation {{ id status }} userErrors {{ field message }} }} }}"""
        bulk_result = shopify_api.execute_graphql(bulk_mutation)
        bulk_op = bulk_result.get("bulkOperationRunMutation", {}).get("bulkOperation")

        if not bulk_op:
            raise Exception(f"Toplu işlem başlatılamadı: {bulk_result.get('bulkOperationRunMutation', {}).get('userErrors')}")

        while bulk_op["status"] in ["CREATED", "RUNNING"]:
            if progress_callback: progress_callback({'progress': 75, 'message': f'Shopify işlemi yürütüyor... (Durum: {bulk_op["status"]})'})
            time.sleep(5)
            status_query = "query { currentBulkOperation { id status errorCode objectCount resultFileUrl } }"
            status_result = shopify_api.execute_graphql(status_query)
            
            new_op_status = status_result.get("currentBulkOperation")
            if new_op_status: bulk_op = new_op_status
            else: logging.warning("Durum kontrol sorgusu boş sonuç döndürdü, önceki durumla devam ediliyor.")

        if progress_callback: progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})

        if bulk_op["status"] == "COMPLETED":
            count = int(bulk_op.get("objectCount", total_updates))
            return {"success": count, "failed": 0, "errors": []}
        else:
            error = f"Toplu işlem başarısız oldu. Durum: {bulk_op['status']}, Hata Kodu: {bulk_op.get('errorCode')}. Detaylar: {bulk_op.get('resultFileUrl')}"
            logging.error(error)
            return {"success": 0, "failed": total_updates, "errors": [error]}
                
    except Exception as e:
        logging.error(f"Toplu fiyat güncelleme sırasında kritik hata: {e}")
        return _update_prices_individually(shopify_api, price_updates, progress_callback)


def _update_prices_individually(shopify_api, price_updates: list, progress_callback=None):
    """Fiyatları tek tek GraphQL mutations ile günceller (fallback metodu)."""
    success_count, failed_count, errors, total = 0, 0, [], len(price_updates)
    
    for i, update in enumerate(price_updates):
        if progress_callback:
            progress = int((i / total) * 100)
            progress_callback({'progress': progress, 'message': f'Tek tek güncelleniyor: {i+1}/{total}'})
        
        # --- DÜZELTME BURADA ---
        # GraphQL sorgu formatı düzeltildi.
        mutation = """
        mutation productVariantUpdate($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant {
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
        
        variant_input = {"id": update["variant_id"], "price": update["price"]}
        if "compare_at_price" in update and update["compare_at_price"] is not None:
            variant_input["compareAtPrice"] = update["compare_at_price"]
        
        try:
            result = shopify_api.execute_graphql(mutation, {"input": variant_input})
            if result.get("productVariantUpdate", {}).get("userErrors"):
                failed_count += 1
                errors.extend(result["productVariantUpdate"]["userErrors"])
                logging.error(f"SKU {update.get('sku')} için fiyat güncellenemedi: {result['productVariantUpdate']['userErrors']}")
            else:
                success_count += 1
                logging.info(f"SKU {update.get('sku')} için fiyat güncellendi.")
        except Exception as e:
            failed_count += 1
            errors.append(str(e))
            logging.error(f"GraphQL sorgusu sırasında hata: {e}")
    
    if progress_callback: progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})
    return {"success": success_count, "failed": failed_count, "errors": errors}