# operations/core_sync.py

import logging

def sync_details(shopify_api, product_gid, sentos_product):
    """Ürünün başlık ve açıklamasını günceller."""
    changes = []
    input_data = {
        "id": product_gid, 
        "title": sentos_product.get('name', '').strip(), 
        "descriptionHtml": sentos_product.get('description_detail') or sentos_product.get('description', '')
    }
    query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
    shopify_api.execute_graphql(query, {'input': input_data})
    changes.append("Başlık ve açıklama güncellendi.")
    logging.info(f"Ürün {product_gid} için temel detaylar güncellendi.")
    return changes

def sync_product_type(shopify_api, product_gid, sentos_product):
    """Ürünün kategorisini (productType) günceller."""
    changes = []
    if category := sentos_product.get('category'):
        input_data = {"id": product_gid, "productType": str(category)}
        query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
        shopify_api.execute_graphql(query, {'input': input_data})
        changes.append(f"Kategori '{category}' olarak ayarlandı.")
        logging.info(f"Ürün {product_gid} için kategori '{category}' olarak ayarlandı.")
    return changes