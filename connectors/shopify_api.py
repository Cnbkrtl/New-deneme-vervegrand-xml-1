# connectors/shopify_api.py

import requests
import time
import json
import logging

class ShopifyAPI:
    """Shopify Admin API ile iletişimi yöneten sınıf."""
    def __init__(self, store_url, access_token):
        if not store_url: raise ValueError("Shopify Mağaza URL'si boş olamaz.")
        if not access_token: raise ValueError("Shopify Erişim Token'ı boş olamaz.")
        
        self.store_url = store_url if store_url.startswith('http') else f"https://{store_url.strip()}"
        self.access_token = access_token
        self.graphql_url = f"{self.store_url}/admin/api/2024-04/graphql.json"
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
            'User-Agent': 'Sentos-Sync-Python/Modular-v1.0'
        }
        self.product_cache = {}
        self.location_id = None

    def _make_request(self, method, url, data=None, is_graphql=False, headers=None, files=None):
        req_headers = headers if headers is not None else self.headers
        try:
            if not is_graphql and not url.startswith('http'):
                 url = f"{self.store_url}/admin/api/2024-04/{url}"
            time.sleep(0.51) # Temel bir gecikme her zaman iyidir.
            response = requests.request(method, url, headers=req_headers, 
                                        json=data if isinstance(data, dict) else None, 
                                        data=data if isinstance(data, bytes) else None,
                                        files=files, timeout=90)
            response.raise_for_status()
            if response.content and 'application/json' in response.headers.get('Content-Type', ''):
                return response.json()
            return response
        except requests.exceptions.RequestException as e:
            error_content = e.response.text if e.response else "No response"
            logging.error(f"Shopify API Bağlantı Hatası ({url}): {e} - Response: {error_content}")
            raise Exception(f"API Hatası: {e} - {error_content}")

    def execute_graphql(self, query, variables=None):
        """
        GraphQL sorgusunu çalıştırır ve hız limitine takıldığında
        otomatik olarak bekleyip tekrar dener (exponential backoff).
        """
        payload = {'query': query, 'variables': variables or {}}
        max_retries = 5
        retry_delay = 1  # Saniye cinsinden başlangıç bekleme süresi

        for attempt in range(max_retries):
            try:
                response_data = self._make_request('POST', self.graphql_url, data=payload, is_graphql=True)
                
                if "errors" in response_data:
                    # Hatanın Throttled olup olmadığını kontrol et
                    is_throttled = any(
                        err.get('extensions', {}).get('code') == 'THROTTLED' 
                        for err in response_data["errors"]
                    )
                    
                    if is_throttled and attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt) # Giderek artan bekleme süresi (1, 2, 4, 8 saniye)
                        logging.warning(f"Hız limitine takıldı (Throttled). {wait_time} saniye beklenip tekrar denenecek... (Deneme {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue # Döngünün başına dön ve tekrar dene
                    
                    # Eğer Throttled değilse veya son deneme ise hatayı yükselt
                    error_messages = [err.get('message', 'Bilinmeyen GraphQL hatası') for err in response_data["errors"]]
                    logging.error(f"GraphQL sorgusu hata verdi: {json.dumps(response_data['errors'], indent=2)}")
                    raise Exception(f"GraphQL Error: {', '.join(error_messages)}")

                return response_data.get("data", {})

            except requests.exceptions.RequestException as e:
                 # Bağlantı hataları için tekrar deneme mantığı da eklenebilir
                 logging.error(f"API bağlantı hatası: {e}. Bu hata için tekrar deneme yapılmıyor.")
                 raise e # Bağlantı hatasını direkt yükselt
        
        raise Exception(f"API isteği {max_retries} denemenin ardından başarısız oldu.")

    def get_all_collections(self, progress_callback=None):
        all_collections = []
        query = """
        query getCollections($cursor: String) {
          collections(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            edges { node { id title } }
          }
        }
        """
        variables = {"cursor": None}
        while True:
            if progress_callback:
                progress_callback(f"Shopify'dan koleksiyonlar çekiliyor... {len(all_collections)} koleksiyon bulundu.")
            data = self.execute_graphql(query, variables)
            collections_data = data.get("collections", {})
            for edge in collections_data.get("edges", []):
                all_collections.append(edge["node"])
            if not collections_data.get("pageInfo", {}).get("hasNextPage"):
                break
            variables["cursor"] = collections_data["pageInfo"]["endCursor"]
        logging.info(f"{len(all_collections)} adet koleksiyon bulundu.")
        return all_collections

    def get_all_products_for_export(self, progress_callback=None):
        all_products = []
        query = """
        query getProductsForExport($cursor: String) {
          products(first: 50, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                title handle
                collections(first: 20) { edges { node { id title } } }
                featuredImage { url }
                variants(first: 100) {
                  edges {
                    node {
                      sku displayName inventoryQuantity
                      selectedOptions { name value }
                      inventoryItem { unitCost { amount } }
                    }
                  }
                }
              }
            }
          }
        }
        """
        variables = {"cursor": None}
        total_fetched = 0
        while True:
            if progress_callback:
                progress_callback(f"Shopify'dan ürün verisi çekiliyor... {total_fetched} ürün alındı.")
            data = self.execute_graphql(query, variables)
            products_data = data.get("products", {})
            for edge in products_data.get("edges", []):
                all_products.append(edge["node"])
            total_fetched = len(all_products)
            if not products_data.get("pageInfo", {}).get("hasNextPage"):
                break
            variables["cursor"] = products_data["pageInfo"]["endCursor"]
        logging.info(f"Export için toplam {len(all_products)} ürün çekildi.")
        return all_products

    def get_variant_ids_by_skus(self, skus: list) -> dict:
        if not skus: return {}
        sanitized_skus = [str(sku).strip() for sku in skus if sku]
        if not sanitized_skus: return {}
        logging.info(f"{len(sanitized_skus)} adet SKU için varyant ID'leri aranıyor...")
        sku_map = {}
        for i in range(0, len(sanitized_skus), 50):
            sku_chunk = sanitized_skus[i:i + 50]
            query_filter = " OR ".join([f"sku:{json.dumps(sku)}" for sku in sku_chunk])
            query = """
            query getVariantIdsBySku($query: String!) {
              productVariants(first: 250, query: $query) {
                edges { node { id sku } }
              }
            }
            """
            try:
                result = self.execute_graphql(query, {"query": query_filter})
                variants = result.get("productVariants", {}).get("edges", [])
                for edge in variants:
                    node = edge.get("node", {})
                    if node.get("sku") and node.get("id"):
                        sku_map[node["sku"]] = node["id"]
            except Exception as e:
                logging.error(f"SKU grubu {i//50+1} için varyant ID'leri alınırken hata: {e}")
        found_skus = set(sku_map.keys())
        all_skus_set = set(sanitized_skus)
        not_found_skus = all_skus_set - found_skus
        if not_found_skus:
            logging.warning(f"Shopify'da bulunamayan {len(not_found_skus)} adet SKU tespit edildi.")
            logging.warning(f"Bulunamayan SKU'lar (ilk 10): {list(not_found_skus)[:10]}")
        logging.info(f"Toplam {len(sku_map)} eşleşen varyant ID'si bulundu.")
        return sku_map

    def get_product_media_details(self, product_gid):
        try:
            query = """
            query getProductMedia($id: ID!) {
                product(id: $id) {
                    media(first: 250) {
                        edges { node { id alt ... on MediaImage { image { originalSrc } } } }
                    }
                }
            }
            """
            result = self.execute_graphql(query, {"id": product_gid})
            media_edges = result.get("product", {}).get("media", {}).get("edges", [])
            media_details = [{'id': n['id'], 'alt': n.get('alt'), 'originalSrc': n.get('image', {}).get('originalSrc')} for n in [e.get('node') for e in media_edges] if n]
            logging.info(f"Ürün {product_gid} için {len(media_details)} mevcut medya bulundu.")
            return media_details
        except Exception as e:
            logging.error(f"Mevcut medya detayları alınırken hata: {e}")
            return []

    def get_default_location_id(self):
        if self.location_id: return self.location_id
        query = "query { locations(first: 1, query: \"status:active\") { edges { node { id } } } }"
        data = self.execute_graphql(query)
        locations = data.get("locations", {}).get("edges", [])
        if not locations: raise Exception("Shopify mağazasında aktif bir envanter lokasyonu bulunamadı.")
        self.location_id = locations[0]['node']['id']
        logging.info(f"Shopify Lokasyon ID'si bulundu: {self.location_id}")
        return self.location_id

    def load_all_products_for_cache(self, progress_callback=None):
        total_loaded = 0
        endpoint = f'{self.store_url}/admin/api/2024-04/products.json?limit=250&fields=id,title,variants'
        
        while endpoint:
            if progress_callback: progress_callback({'message': f"Shopify ürünleri önbelleğe alınıyor... {total_loaded} ürün bulundu."})
            
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            products = response.json().get('products', [])
            
            for product in products:
                product_data = {'id': product['id'], 'gid': f"gid://shopify/Product/{product['id']}"}
                if title := product.get('title'): self.product_cache[f"title:{title.strip()}"] = product_data
                for variant in product.get('variants', []):
                    if sku := variant.get('sku'): self.product_cache[f"sku:{sku.strip()}"] = product_data
            
            total_loaded += len(products)
            link_header = response.headers.get('Link', '')
            endpoint = next((link['url'] for link in requests.utils.parse_header_links(link_header) if link.get('rel') == 'next'), None)
        
        logging.info(f"Shopify'dan toplam {total_loaded} ürün önbelleğe alındı.")
        return total_loaded