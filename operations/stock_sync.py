# operations/stock_sync.py

import logging
import time
from utils import get_variant_color, get_variant_size, get_apparel_sort_key
import json 

def sync_stock_and_variants(shopify_api, product_gid, sentos_product):
    """Bir ürünün varyantlarını ve stoklarını senkronize eder."""
    changes = []
    logging.info(f"Ürün {product_gid} için varyantlar ve stoklar senkronize ediliyor...")
    
    ex_vars = _get_shopify_variants(shopify_api, product_gid)
    ex_skus = {str(v.get('inventoryItem',{}).get('sku','')).strip() for v in ex_vars if v.get('inventoryItem',{}).get('sku')}
    s_vars = sentos_product.get('variants', []) or [sentos_product]
    
    new_vars = [v for v in s_vars if str(v.get('sku','')).strip() not in ex_skus]
    if new_vars:
        msg = f"{len(new_vars)} yeni varyant eklendi."
        changes.append(msg)
        _add_variants(shopify_api, product_gid, new_vars, sentos_product)
        time.sleep(3) # Varyantların işlenmesi için bekle
    
    all_now_variants = _get_shopify_variants(shopify_api, product_gid)
    if adjustments := _prepare_inventory_adjustments(s_vars, all_now_variants):
        msg = f"{len(adjustments)} varyantın stok seviyesi güncellendi."
        changes.append(msg)
        _adjust_inventory(shopify_api, adjustments)

    # NOTE: _sync_product_options fonksiyonu kaldırıldı.
    # Shopify'da ürün seçeneklerini güncellemek için daha iyi bir yol yok.
    # Ancak, varyantlar oluşturulurken veya güncellenirken seçenekler doğru ayarlanıyor.
        
    if not new_vars and not adjustments:
        changes.append("Stok ve varyantlar kontrol edildi (Değişiklik yok).")
        
    logging.info(f"Ürün {product_gid} için varyant ve stok senkronizasyonu tamamlandı.")
    return changes

def _get_shopify_variants(shopify_api, product_gid):
    q="""query gPV($id:ID!){product(id:$id){variants(first:250){edges{node{id inventoryItem{id sku}}}}}}"""
    data=shopify_api.execute_graphql(q,{"id":product_gid})
    return [e['node'] for e in data.get("product",{}).get("variants",{}).get("edges",[])]

def _prepare_inventory_adjustments(sentos_variants, shopify_variants):
    sku_map = {str(v.get('inventoryItem',{}).get('sku','')).strip():v.get('inventoryItem',{}).get('id') for v in shopify_variants if v.get('inventoryItem',{}).get('sku')}
    adjustments = []
    for v in sentos_variants:
        sku = str(v.get('sku','')).strip()
        if sku and (iid := sku_map.get(sku)):
            qty = sum(s.get('stock', 0) for s in v.get('stocks', []) if s)
            adjustments.append({"inventoryItemId": iid, "availableQuantity": int(qty)})
    return adjustments

def _adjust_inventory(shopify_api, adjustments):
    if not adjustments: return
    location_id = shopify_api.get_default_location_id()
    mutation = """
    mutation inventorySetOnHandQuantities($input: InventorySetOnHandQuantitiesInput!) {
      inventorySetOnHandQuantities(input: $input) { userErrors { field message code } }
    }
    """
    variables = { "input": { "reason": "correction", "setQuantities": [ { "inventoryItemId": adj["inventoryItemId"], "quantity": adj["availableQuantity"], "locationId": location_id } for adj in adjustments ] } }
    try:
        shopify_api.execute_graphql(mutation, variables)
    except Exception as e:
        logging.error(f"Toplu stok güncelleme sırasında hata: {e}")

def _add_variants(shopify_api, product_gid, new_variants, main_product):
    # Fiyatlandırma mantığı buraya da eklenebilir, şimdilik 0.0 kabul ediliyor
    price = 0.0 
    v_in = []
    for v in new_variants:
        vi = {"price": f"{price:.2f}", "inventoryItem": {"tracked": True, "sku": v.get('sku', '')}, "barcode": v.get('barcode')}
        options = []
        if color := get_variant_color(v): options.append(color)
        if size := get_variant_size(v): options.append(size)
        vi['options'] = options
        v_in.append(vi)

    bulk_q="""mutation pVBC($pId:ID!,$v:[ProductVariantInput!]!){productVariantsBulkCreate(productId:$pId,variants:$v){productVariants{id inventoryItem{id sku}} userErrors{field message}}}"""
    res=shopify_api.execute_graphql(bulk_q,{"pId":product_gid,"v":v_in})
    # ... Hata yönetimi ve aktivasyon eklenebilir ...

# NOTE: productUpdate mutasyonu ile options alanını güncellemeye çalışan
# _sync_product_options fonksiyonu kaldırılmıştır. Bu işlev, varyant oluşturma
# sırasında zaten doğru bir şekilde gerçekleştirilmektedir.