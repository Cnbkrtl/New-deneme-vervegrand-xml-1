# operations/price_sync.py (Tamamen Yeniden Yazılmış Sürüm)

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
        return {"success": 0, "failed": 0, "errors": ["Gönderilecek veri bulunamadı."], "details": []}

    if progress_callback: progress_callback({'progress': 15, 'message': 'Varyantlar Shopify ile eşleştiriliyor...'})
    skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
    variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)

    updates = []
    for _, row in df_to_send.iterrows():
        sku = str(row['MODEL KODU'])
        if sku in variant_map:
            payload = {"id": variant_map[sku], "price": f"{row[price_column_name]:.2f}", "sku": sku}
            if compare_price_column_name and row.get(compare_price_column_name) is not None:
                payload["compareAtPrice"] = f"{row[compare_price_column_name]:.2f}"
            updates.append(payload)
        else:
            logging.warning(f"SKU {sku} için Shopify'da eşleşen varyant bulunamadı. Fiyat güncellemesi atlandı.")
    
    if not updates:
        logging.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")
        return {"success": 0, "failed": len(skus_to_update), "errors": ["Shopify'da eşleşen SKU bulunamadı."], "details": []}

    logging.info(f"{len(updates)} adet varyant fiyat güncellemesi için toplu işlem başlatılıyor.")
    return _update_variant_prices_in_bulk(shopify_api, updates, progress_callback)


def _update_variant_prices_in_bulk(shopify_api, price_updates: list, progress_callback=None):
    total_updates = len(price_updates)
    
    try:
        if progress_callback: progress_callback({'progress': 20, 'message': f'{total_updates} varyant için güncelleme dosyası hazırlanıyor...'})
        
        jsonl_data = ""
        for update in price_updates:
            # Sadece Shopify'ın beklediği alanları al
            payload = {
                "id": update["id"],
                "price": update["price"],
            }
            if "compareAtPrice" in update:
                payload["compareAtPrice"] = update["compareAtPrice"]
            
            jsonl_data += json.dumps({"input": payload}) + "\n"
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
        
        bulk_mutation = f"""
mutation {{
    bulkOperationRunMutation(
        mutation: "mutation($input: ProductVariantInput!) {{ productVariantUpdate(input: $input) {{ productVariant {{ id }} userErrors {{ field message }} }} }}", 
        stagedUploadPath: "{target['resourceUrl']}"
    ) {{
        bulkOperation {{
            id
            status
            url
        }}
        userErrors {{
            field
            message
        }}
    }}
}}
"""
        bulk_result = shopify_api.execute_graphql(bulk_mutation)
        bulk_op = bulk_result.get("bulkOperationRunMutation", {}).get("bulkOperation")

        if not bulk_op:
            raise Exception(f"Toplu işlem başlatılamadı: {bulk_result.get('bulkOperationRunMutation', {}).get('userErrors')}")
        
        logging.info(f"Toplu işlem başlatıldı. ID: {bulk_op['id']}, Durum: {bulk_op['status']}")

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
            logging.info(f"Toplu fiyat güncelleme işlemi başarıyla tamamlandı. {count} varyant güncellendi.")
            return {"success": count, "failed": 0, "errors": [], "details": [{"status": "success", "message": f"{count} varyant başarıyla güncellendi."}]}
        else:
            error_message = f"Toplu işlem başarısız oldu. Durum: {bulk_op['status']}, Hata Kodu: {bulk_op.get('errorCode')}. Detaylar: {bulk_op.get('resultFileUrl')}"
            logging.error(error_message)
            return {"success": 0, "failed": total_updates, "errors": [error_message], "details": [{"status": "failed", "reason": error_message}]}
                
    except Exception as e:
        logging.error(f"Toplu fiyat güncelleme sırasında kritik hata: {e}")
        return {"success": 0, "failed": total_updates, "errors": [str(e)], "details": [{"status": "failed", "reason": str(e)}]}