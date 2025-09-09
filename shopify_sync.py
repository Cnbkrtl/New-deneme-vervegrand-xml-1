# shopify_sync.py (Throttling Hatasına Karşı Otomatik Yeniden Deneme Eklendi v4)

"""
Sentos API'den Shopify'a Ürün Senkronizasyonu Mantık Dosyası
Versiyon 23.6: Throttling (API Limit) Hatasına Karşı Sağlamlaştırma
- GÜNCELLEME: `execute_graphql` fonksiyonuna "exponential backoff" ile otomatik yeniden deneme mekanizması eklendi.
- Bu sayede, yoğun istek anlarında alınan "Throttled" hataları otomatik olarak yönetilir ve senkronizasyonun kesilmesi engellenir.
"""
import requests
import time
import json
import threading
import logging
import traceback
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.auth import HTTPBasicAuth
from urllib.parse import urljoin, urlparse
from datetime import timedelta
import os

# --- Loglama Konfigürasyonu ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Shopify API Entegrasyon Sınıfı ---
class ShopifyAPI:
    def __init__(self, store_url, access_token):
        if not store_url: raise ValueError("Shopify Mağaza URL'si boş olamaz.")
        if not access_token: raise ValueError("Shopify Erişim Token'ı boş olamaz.")
        
        self.store_url = store_url if store_url.startswith('http') else f"https://{store_url.strip()}"
        self.access_token = access_token
        self.graphql_url = f"{self.store_url}/admin/api/2024-04/graphql.json"
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
            'User-Agent': 'Sentos-Sync-Python/23.6-Throttling-Retry'
        }
        self.product_cache = {}
        self.location_id = None

    def _make_request(self, method, url, data=None, is_graphql=False, headers=None, files=None):
        req_headers = headers if headers is not None else self.headers
        
        try:
            if not is_graphql and not url.startswith('http'):
                 url = f"{self.store_url}/admin/api/2024-04/{url}"

            # API limitlerine takılmamak için her istek arasında küçük bir bekleme süresi koymak iyi bir pratiktir.
            time.sleep(0.51) 
            
            response = requests.request(method, url, headers=req_headers, 
                                        json=data if isinstance(data, dict) else None, 
                                        data=data if isinstance(data, bytes) else None,
                                        files=files,
                                        timeout=90)
            
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
        GraphQL sorgusunu çalıştırır ve 'Throttled' hatası durumunda
        otomatik olarak yeniden deneme yapar.
        """
        payload = {'query': query, 'variables': variables or {}}
        max_retries = 5
        initial_backoff = 1.0  # saniye

        for attempt in range(max_retries):
            try:
                response_data = self._make_request('POST', self.graphql_url, data=payload, is_graphql=True)
                
                if "errors" in response_data:
                    # Hatanın 'Throttled' olup olmadığını kontrol et
                    is_throttled = any(
                        err.get("extensions", {}).get("code") == "THROTTLED"
                        for err in response_data["errors"]
                    )

                    if is_throttled and attempt < max_retries - 1:
                        wait_time = initial_backoff * (2 ** attempt)
                        logging.warning(
                            f"GraphQL isteği API limitine takıldı (Throttled). "
                            f"{wait_time:.2f} saniye sonra yeniden denenecek... (Deneme {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue  # Döngünün başına dön ve tekrar dene
                    else:
                        # Throttled değilse veya son deneme de başarısızsa hatayı yükselt
                        error_messages = [err.get('message', 'Bilinmeyen GraphQL hatası') for err in response_data["errors"]]
                        logging.error(f"GraphQL sorgusu hata verdi: {json.dumps(response_data['errors'], indent=2)}")
                        raise Exception(f"GraphQL Error: {', '.join(error_messages)}")

                return response_data.get("data", {})

            except Exception as e:
                # _make_request'ten gelen diğer hataları yakala
                logging.error(f"GraphQL yürütme sırasında kritik hata: {e}")
                if attempt < max_retries - 1:
                    wait_time = initial_backoff * (2 ** attempt)
                    time.sleep(wait_time) # Bağlantı hatalarında da beklemek faydalı olabilir
                else:
                    raise  # Tüm denemeler başarısız olursa son hatayı yükselt

        # Bu noktaya gelinmemeli, ancak güvenlik için bir fallback
        raise Exception(f"GraphQL sorgusu {max_retries} denemenin ardından başarısız oldu.")

    def _get_product_media_details(self, product_gid):
        try:
            query = """
            query getProductMedia($id: ID!) {
                product(id: $id) {
                    media(first: 250) {
                        edges {
                            node {
                                id
                                alt
                                ... on MediaImage {
                                    image {
                                        originalSrc
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            result = self.execute_graphql(query, {"id": product_gid})
            media_edges = result.get("product", {}).get("media", {}).get("edges", [])
            
            media_details = []
            for edge in media_edges:
                node = edge.get('node')
                if node:
                    media_details.append({
                        'id': node['id'],
                        'alt': node.get('alt'),
                        'originalSrc': node.get('image', {}).get('originalSrc')
                    })
            
            logging.info(f"Ürün {product_gid} için {len(media_details)} mevcut medya bulundu.")
            return media_details
        except Exception as e:
            logging.error(f"Mevcut medya detayları alınırken hata: {e}")
            return []

    def delete_product_media(self, product_id, media_ids):
        if not media_ids: return
        logging.info(f"Ürün GID: {product_id} için {len(media_ids)} medya siliniyor...")
        query = """
        mutation productDeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
            productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
                deletedMediaIds
                userErrors { field message }
            }
        }
        """
        try:
            result = self.execute_graphql(query, {'productId': product_id, 'mediaIds': media_ids})
            deleted_ids = result.get('productDeleteMedia', {}).get('deletedMediaIds', [])
            errors = result.get('productDeleteMedia', {}).get('userErrors', [])
            if errors: logging.warning(f"Medya silme hataları: {errors}")
            logging.info(f"{len(deleted_ids)} medya başarıyla silindi.")
        except Exception as e:
            logging.error(f"Medya silinirken kritik hata oluştu: {e}")

    def reorder_product_media(self, product_id, media_ids):
        if not media_ids or len(media_ids) < 2:
            logging.info("Yeniden sıralama için yeterli medya bulunmuyor (1 veya daha az).")
            return

        moves = [{"id": media_id, "newPosition": str(i)} for i, media_id in enumerate(media_ids)]
        
        logging.info(f"Ürün {product_id} için {len(moves)} medya yeniden sıralama iş emri gönderiliyor...")
        
        query = """
        mutation productReorderMedia($id: ID!, $moves: [MoveInput!]!) {
          productReorderMedia(id: $id, moves: $moves) {
            userErrors {
              field
              message
            }
          }
        }
        """
        try:
            result = self.execute_graphql(query, {'id': product_id, 'moves': moves})
            
            errors = result.get('productReorderMedia', {}).get('userErrors', [])
            if errors:
                logging.warning(f"Medya yeniden sıralama hataları: {errors}")
            else:
                logging.info("✅ Medya yeniden sıralama iş emri başarıyla gönderildi.")
        except Exception as e:
            logging.error(f"Medya yeniden sıralanırken kritik hata: {e}")

    def get_default_location_id(self):
        if self.location_id: return self.location_id
        query = "query { locations(first: 1, query: \"status:active\") { edges { node { id } } } }"
        data = self.execute_graphql(query)
        locations = data.get("locations", {}).get("edges", [])
        if not locations: raise Exception("Shopify mağazasında aktif bir envanter lokasyonu bulunamadı.")
        self.location_id = locations[0]['node']['id']
        logging.info(f"Shopify Lokasyon ID'si bulundu: {self.location_id}")
        return self.location_id

    def load_all_products(self, progress_callback=None):
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
    
    def test_connection(self):
        query = "query { shop { name url currencyCode plan { displayName } } }"
        data = self.execute_graphql(query)
        shop_data = data.get('shop', {})
        products_count = self._make_request('GET', 'products/count.json').get('count', 0)
        return {
            'name': shop_data.get('name', 'N/A'), 'domain': shop_data.get('url', '').replace('https://', ''),
            'products_count': products_count, 'currency': shop_data.get('currencyCode', 'N/A'),
            'plan': shop_data.get('plan', {}).get('displayName', 'N/A')
        }

    def get_all_collections(self, progress_callback=None):
        all_collections = []
        query = """
        query getCollections($cursor: String) {
          collections(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                id
                title
              }
            }
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
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                title
                handle
                collections(first: 20) {
                  edges {
                    node {
                      id
                      title
                    }
                  }
                }
                featuredImage {
                  url
                }
                variants(first: 100) {
                  edges {
                    node {
                      sku
                      displayName
                      inventoryQuantity
                      selectedOptions {
                        name
                        value
                      }
                      inventoryItem {
                        unitCost {
                          amount
                        }
                      }
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

    def update_variant_prices_individually(self, price_updates: list, progress_callback=None) -> dict:
        """Fiyatları tek tek GraphQL mutations ile günceller (staged upload yerine)"""
        if not price_updates:
            return {"success": 0, "failed": 0, "errors": []}
        
        success_count = 0
        failed_count = 0
        errors = []
        total = len(price_updates)
        
        for i, update in enumerate(price_updates):
            if progress_callback:
                progress = int((i / total) * 100)
                progress_callback({'progress': progress, 'message': f'Güncelleniyor: {i+1}/{total}'})
            
            mutation = """
            mutation ($input: ProductVariantInput!) {
                productVariantUpdate(input: $input) {
                    productVariant { id }
                    userErrors { field message }
                }
            }
            """
            
            variant_input = {
                "id": update["variant_id"],
                "price": update["price"]
            }
            if "compare_at_price" in update and update["compare_at_price"] is not None:
                variant_input["compareAtPrice"] = update["compare_at_price"]
            
            try:
                result = self.execute_graphql(mutation, {"input": variant_input})
                if result.get("productVariantUpdate", {}).get("userErrors"):
                    failed_count += 1
                    errors.extend(result["productVariantUpdate"]["userErrors"])
                else:
                    success_count += 1
                time.sleep(0.2)  # Rate limiting
            except Exception as e:
                failed_count += 1
                errors.append(str(e))
        
        if progress_callback:
            progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})
        
        return {"success": success_count, "failed": failed_count, "errors": errors}

    def bulk_update_variant_prices(self, price_updates: list, progress_callback=None) -> dict:
        if not price_updates:
            return {"success": 0, "failed": 0, "errors": []}
        
        # Eğer 50'den az güncelleme varsa, tek tek güncelle (daha güvenilir)
        if len(price_updates) <= 50:
            return self.update_variant_prices_individually(price_updates, progress_callback)
        
        # 50'den fazla güncelleme için staged upload kullan
        try:
            if progress_callback: progress_callback({'progress': 10, 'message': 'Güncelleme dosyası hazırlanıyor...'})
            
            jsonl_data = ""
            for update in price_updates:
                price_input = {"id": update["variant_id"], "price": update["price"]}
                if "compare_at_price" in update and update["compare_at_price"] is not None:
                    price_input["compareAtPrice"] = update["compare_at_price"]
                jsonl_data += json.dumps({"input": price_input}) + "\n"
            jsonl_bytes = jsonl_data.encode('utf-8')

            if progress_callback: progress_callback({'progress': 25, 'message': 'Shopify yükleme alanı hazırlanıyor...'})
            upload_mutation = """
            mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
                stagedUploadsCreate(input: $input) {
                    stagedTargets { url resourceUrl parameters { name value } }
                    userErrors { field message }
                }
            }
            """
            upload_vars = { "input": [{ "resource": "BULK_MUTATION_VARIABLES", "filename": "price_updates.jsonl", "mimeType": "application/jsonl", "httpMethod": "POST" }] }
            upload_result = self.execute_graphql(upload_mutation, upload_vars)
            
            staged_data = upload_result.get("stagedUploadsCreate")
            if not staged_data or not staged_data.get("stagedTargets"):
                user_errors = staged_data.get("userErrors", []) if staged_data else "stagedUploadsCreate mutation'ı null (boş) sonuç döndürdü."
                error_message = f"Staged upload URL'i alınamadı. Sebebi: {user_errors}"
                logging.error(error_message)
                raise Exception(error_message)

            target = staged_data["stagedTargets"][0]
            upload_url = target["url"]
            staged_resource_url = target["resourceUrl"]
            
            if progress_callback: progress_callback({'progress': 40, 'message': 'Veriler Shopify\'a yükleniyor...'})
            
            form_data = {param['name']: param['value'] for param in target['parameters']}
            files = {'file': ('price_updates.jsonl', jsonl_bytes, 'application/jsonl')}
            
            try:
                upload_response = requests.post(upload_url, data=form_data, files=files, timeout=90)
                upload_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                error_content = e.response.text if e.response else "No response body"
                logging.error(f"Staged upload sırasında hata oluştu. URL: {upload_url}, Status: {e.response.status_code if e.response else 'N/A'}, Response: {error_content}")
                logging.info("Staged upload başarısız oldu, tek tek güncelleme yöntemine geçiliyor...")
                return self.update_variant_prices_individually(price_updates, progress_callback)

            if progress_callback: progress_callback({'progress': 55, 'message': 'Toplu güncelleme işlemi başlatılıyor...'})
            bulk_mutation = f"""
            mutation {{
                bulkOperationRunMutation(
                    mutation: "mutation call($input: ProductVariantInput!) {{ productVariantUpdate(input: $input) {{ productVariant {{ id }} userErrors {{ field message }} }} }}",
                    stagedUploadPath: "{staged_resource_url}"
                ) {{
                    bulkOperation {{ id status }}
                    userErrors {{ field message }}
                }}
            }}
            """
            bulk_result = self.execute_graphql(bulk_mutation)
            bulk_op = bulk_result["bulkOperationRunMutation"]["bulkOperation"]
            
            while bulk_op["status"] in ["CREATED", "RUNNING"]:
                if progress_callback: progress_callback({'progress': 75, 'message': f'Shopify işlemi yürütüyor... (Durum: {bulk_op["status"]})'})
                time.sleep(5)
                status_query = "query { currentBulkOperation { id status errorCode objectCount } }"
                status_result = self.execute_graphql(status_query)
                bulk_op = status_result["currentBulkOperation"]

            if progress_callback: progress_callback({'progress': 100, 'message': 'İşlem tamamlandı!'})

            if bulk_op["status"] == "COMPLETED":
                count = int(bulk_op.get("objectCount", len(price_updates)))
                return {"success": count, "failed": 0, "errors": []}
            else:
                error = f"Toplu işlem başarısız oldu. Durum: {bulk_op['status']}, Hata Kodu: {bulk_op.get('errorCode')}"
                return {"success": 0, "failed": len(price_updates), "errors": [error]}
                
        except Exception as e:
            logging.error(f"Bulk update hatası: {e}. Tek tek güncellemeye geçiliyor...")
            return self.update_variant_prices_individually(price_updates, progress_callback)

# ... (SentosAPI ve diğer sınıflar/fonksiyonlar değişmeden kalır) ...
class SentosAPI:
    def __init__(self, api_url, api_key, api_secret, api_cookie=None):
        self.api_url = api_url.strip().rstrip('/')
        self.auth = HTTPBasicAuth(api_key, api_secret)
        self.api_cookie = api_cookie
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _make_request(self, method, endpoint, auth_type='basic', data=None, params=None, is_internal_call=False):
        if is_internal_call:
            parsed_url = urlparse(self.api_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            url = f"{base_url}{endpoint}"
        else:
            url = urljoin(self.api_url + '/', endpoint.lstrip('/'))
        
        headers = self.headers.copy()
        auth = None
        
        if auth_type == 'cookie':
            if not self.api_cookie:
                raise ValueError("Cookie ile istek için Sentos API Cookie ayarı gereklidir.")
            headers['Cookie'] = self.api_cookie
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            auth = self.auth

        try:
            response = requests.request(method, url, headers=headers, auth=auth, data=data, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise Exception(f"Sentos API Hatası ({url}): {e}")
    
    def get_all_products(self, progress_callback=None, page_size=100):
        all_products, page = [], 1
        total_elements = None
        start_time = time.monotonic()

        while True:
            endpoint = f"/products?page={page}&size={page_size}"
            try:
                response = self._make_request("GET", endpoint).json()
                products_on_page = response.get('data', [])
                
                if not products_on_page and page > 1: break
                all_products.extend(products_on_page)
                
                if total_elements is None: 
                    total_elements = response.get('total_elements', 'Bilinmiyor')

                if progress_callback:
                    elapsed_time = time.monotonic() - start_time
                    message = (
                        f"Sentos'tan ürünler çekiliyor ({len(all_products)} / {total_elements})... "
                        f"Geçen süre: {int(elapsed_time)}s"
                    )
                    progress = int((len(all_products) / total_elements) * 100) if isinstance(total_elements, int) and total_elements > 0 else 0
                    progress_callback({'message': message, 'progress': progress})
                
                if len(products_on_page) < page_size: break
                page += 1
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Sayfa {page} çekilirken hata: {e}")
                raise Exception(f"Sentos API'den ürünler çekilemedi: {e}")
            
        logging.info(f"Sentos'tan toplam {len(all_products)} ürün çekildi.")
        return all_products

    def get_ordered_image_urls(self, product_id):
        if not self.api_cookie:
            logging.warning(f"Sentos Cookie ayarlanmadığı için sıralı resimler alınamıyor (Ürün ID: {product_id}).")
            return None

        try:
            endpoint = "/urun_sayfalari/include/ajax/fetch_urunresimler.php"
            payload = {
                'draw': '1', 'start': '0', 'length': '100',
                'search[value]': '', 'search[regex]': 'false',
                'urun': product_id, 'model': '0', 'renk': '0',
                'order[0][column]': '0', 'order[0][dir]': 'desc'
            }

            logging.info(f"Ürün ID {product_id} için sıralı resimler çekiliyor...")
            response = self._make_request("POST", endpoint, auth_type='cookie', data=payload, is_internal_call=True)
            response_json = response.json()

            ordered_urls = []
            for item in response_json.get('data', []):
                if len(item) > 2:
                    html_string = item[2]
                    match = re.search(r'href="(https?://[^"]+/o_[^"]+)"', html_string)
                    if match:
                        ordered_urls.append(match.group(1))

            logging.info(f"{len(ordered_urls)} adet sıralı resim URL'si bulundu.")
            return ordered_urls
        except ValueError as ve:
            logging.error(f"Resim sırası alınamadı: {ve}")
            return None
        except Exception as e:
            logging.error(f"Sıralı resimler çekilirken hata oluştu (Ürün ID: {product_id}): {e}")
            return []

    def test_connection(self):
        try:
            response = self._make_request("GET", "/products?page=1&size=1").json()
            return {'success': True, 'total_products': response.get('total_elements', 0), 'message': 'REST API OK'}
        except Exception as e:
            return {'success': False, 'message': f'REST API failed: {e}'}

    def get_product_by_sku(self, sku):
        if not sku:
            raise ValueError("Aranacak SKU boş olamaz.")
        endpoint = f"/products?sku={sku.strip()}"
        try:
            response = self._make_request("GET", endpoint).json()
            products = response.get('data', [])
            if not products:
                logging.warning(f"Sentos API'de '{sku}' SKU'su ile ürün bulunamadı.")
                return None
            logging.info(f"Sentos API'de '{sku}' SKU'su ile ürün bulundu.")
            return products[0]
        except Exception as e:
            logging.error(f"Sentos'ta SKU '{sku}' aranırken hata: {e}")
            raise


class ProductSyncManager:
    def __init__(self, shopify_api, sentos_api):
        self.shopify = shopify_api
        self.sentos = sentos_api
        self.stats = {'total': 0, 'created': 0, 'updated': 0, 'failed': 0, 'skipped': 0, 'processed': 0}
        self.details = []
        self._lock = threading.Lock()

    def find_shopify_product(self, sentos_product):
        if sku := sentos_product.get('sku', '').strip():
            if product := self.shopify.product_cache.get(f"sku:{sku}"): return product
        if name := sentos_product.get('name', '').strip():
            if product := self.shopify.product_cache.get(f"title:{name}"): return product
        return None
    
    def _get_apparel_sort_key(self, size_str):
        if not isinstance(size_str, str): return (3, 9999, size_str)
        size_upper = size_str.strip().upper()
        size_order_map = {'XXS': 0, 'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, 'XXL': 6, '2XL': 6, '3XL': 7, 'XXXL': 7, '4XL': 8, 'XXXXL': 8, '5XL': 9, 'XXXXXL': 9, 'TEK EBAT': 100, 'STANDART': 100}
        if size_upper in size_order_map: return (1, size_order_map[size_upper], size_str)
        numbers = re.findall(r'\d+', size_str)
        if numbers: return (2, int(numbers[0]), size_str)
        return (3, 9999, size_str)

    def _prepare_basic_product_input(self, p):
        i = {"title": p.get('name','').strip(),"descriptionHtml":p.get('description_detail')or p.get('description',''),"vendor":"Vervegrand","status":"ACTIVE"}
        if cat:=p.get('category'): i['productType']=str(cat)
        i['tags'] = sorted(list({'Vervegrand', str(p.get('category'))} if p.get('category') else {'Vervegrand'}))
        v = p.get('variants',[]) or [p]
        c = sorted(list(set(self._get_variant_color(x) for x in v if self._get_variant_color(x))))
        unique_sizes = list(set(self._get_variant_size(x) for x in v if self._get_variant_size(x)))
        s = sorted(unique_sizes, key=self._get_apparel_sort_key)
        o=[]
        if c:o.append({"name":"Renk","values":[{"name":x} for x in c]})
        if s:o.append({"name":"Beden","values":[{"name":x} for x in s]})
        if o:i['productOptions']=o
        return i

    def _sync_product_options(self, product_gid, sentos_product):
        v = sentos_product.get('variants', []) or [sentos_product]
        colors = sorted(list(set(self._get_variant_color(x) for x in v if self._get_variant_color(x))))
        unique_sizes = list(set(self._get_variant_size(x) for x in v if self._get_variant_size(x)))
        sizes = sorted(unique_sizes, key=self._get_apparel_sort_key)
        options_input = []
        if colors:
            options_input.append({"name": "Renk", "values": [{"name": c} for c in colors]})
        if sizes:
            options_input.append({"name": "Beden", "values": [{"name": s} for s in sizes]})
        if not options_input: return
        query = "mutation productOptionsReorder($productId: ID!, $options: [OptionReorderInput!]!) { productOptionsReorder(productId: $productId, options: $options) { userErrors { field message } } }"
        variables = {"productId": product_gid, "options": options_input}
        try:
            self.shopify.execute_graphql(query, variables)
        except Exception as e:
            logging.error(f"Seçenek sıralama sırasında kritik hata: {e}")

    def _prepare_variant_bulk_input(self, v, mp, c=False):
        o=[];pr=self._calculate_price(v,mp)
        if cl:=self._get_variant_color(v):o.append({"optionName":"Renk","name":cl})
        if sz:=self._get_variant_size(v):o.append({"optionName":"Beden","name":sz})
        vi={"price":f"{pr:.2f}","inventoryItem":{"tracked":True}}
        if c:vi["inventoryItem"]["sku"]=v.get('sku','')
        if o:vi['optionValues']=o
        if b:=v.get('barcode'):vi['barcode']=b
        return vi

    def _calculate_price(self, variant, main_product):
        if prices := main_product.get('prices', {}).get('shopify', {}):
            for key in ['sale_price', 'list_price']:
                if val_str := prices.get(key, '0'):
                    try:
                        price = float(str(val_str).replace(',', '.'))
                        if price > 0: return price
                    except (ValueError, TypeError): continue
        if main_price_str := main_product.get('sale_price', '0'):
            try: return float(str(main_price_str).replace(',', '.'))
            except (ValueError, TypeError): pass
        return 0.0
            
    def _add_new_media_to_product(self, product_gid, urls_to_add, product_title, set_alt_text=False):
        if not urls_to_add: return
        media_input = []
        for url in urls_to_add:
            alt_text = product_title if set_alt_text else url
            media_input.append({"originalSource": url, "alt": alt_text, "mediaContentType": "IMAGE"})
        for i in range(0, len(media_input), 10):
            batch = media_input[i:i + 10]
            try:
                query = "mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) { productCreateMedia(productId: $productId, media: $media) { media { id } mediaUserErrors { field message } } }"
                self.shopify.execute_graphql(query, {'productId': product_gid, 'media': batch})
            except Exception as e:
                logging.error(f"Medya batch {i//10 + 1} eklenirken hata: {e}")

    def _sync_product_media(self, product_gid, sentos_product, set_alt_text=False):
        changes = []
        product_title = sentos_product.get('name', '').strip()
        sentos_ordered_urls = self.sentos.get_ordered_image_urls(sentos_product.get('id'))
        
        if sentos_ordered_urls is None:
             changes.append("Medya senkronizasyonu atlandı (Cookie eksik).")
             return changes
        
        initial_shopify_media = self.shopify._get_product_media_details(product_gid)
        
        if not sentos_ordered_urls:
            if media_ids_to_delete := [m['id'] for m in initial_shopify_media]:
                self.shopify.delete_product_media(product_gid, media_ids_to_delete)
                changes.append(f"{len(media_ids_to_delete)} Shopify görseli silindi.")
            return changes
            
        shopify_src_map = {m['originalSrc']: m for m in initial_shopify_media if m.get('originalSrc')}
        media_ids_to_delete = [media['id'] for src, media in shopify_src_map.items() if src not in sentos_ordered_urls]
        urls_to_add = [url for url in sentos_ordered_urls if url not in shopify_src_map]
        
        media_changed = False
        if urls_to_add:
            changes.append(f"{len(urls_to_add)} yeni görsel eklendi.")
            self._add_new_media_to_product(product_gid, urls_to_add, product_title, set_alt_text)
            media_changed = True
            
        if media_ids_to_delete:
            changes.append(f"{len(media_ids_to_delete)} eski görsel silindi.")
            self.shopify.delete_product_media(product_gid, media_ids_to_delete)
            media_changed = True
            
        if media_changed:
            changes.append("Görsel sırası güncellendi.")
            time.sleep(10)
            
            final_shopify_media = self.shopify._get_product_media_details(product_gid)
            final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
            ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]

            if len(ordered_media_ids) < len(sentos_ordered_urls):
                logging.warning(f"Alt etiketi eşleştirme sorunu: {len(sentos_ordered_urls)} resim beklenirken {len(ordered_media_ids)} ID bulundu. Sıralama eksik olabilir.")

            self.shopify.reorder_product_media(product_gid, ordered_media_ids)
        
        if not changes and not media_changed:
            changes.append("Resimler kontrol edildi (Değişiklik yok).")
            
        return changes

    def _get_variant_size(self, variant):
        model = variant.get('model', "")
        return (model.get('value', "") if isinstance(model, dict) else str(model)).strip() or None

    def _get_variant_color(self, variant):
        return (variant.get('color') or "").strip() or None

    def _sync_core_details(self, product_gid, sentos_product):
        changes = []
        input_data = {"id": product_gid, "title": sentos_product.get('name', '').strip(), "descriptionHtml": sentos_product.get('description_detail') or sentos_product.get('description', '')}
        query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
        self.shopify.execute_graphql(query, {'input': input_data})
        changes.append("Başlık ve açıklama güncellendi.")
        return changes

    def _sync_product_type(self, product_gid, sentos_product):
        changes = []
        if category := sentos_product.get('category'):
            input_data = {"id": product_gid, "productType": str(category)}
            query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
            self.shopify.execute_graphql(query, {'input': input_data})
            changes.append(f"Kategori '{category}' olarak ayarlandı.")
        return changes
    
    def _get_product_variants(self, product_gid):
        q="""query gPV($id:ID!){product(id:$id){variants(first:250){edges{node{id inventoryItem{id sku}}}}}}"""
        data=self.shopify.execute_graphql(q,{"id":product_gid})
        return [e['node'] for e in data.get("product",{}).get("variants",{}).get("edges",[])]

    def _prepare_inventory_adjustments(self, sentos_variants, shopify_variants):
        sku_map = {str(v.get('inventoryItem',{}).get('sku','')).strip():v.get('inventoryItem',{}).get('id') for v in shopify_variants if v.get('inventoryItem',{}).get('sku')}
        adjustments = []
        for v in sentos_variants:
            sku = str(v.get('sku','')).strip()
            if sku and (iid := sku_map.get(sku)):
                qty = 0
                if s := v.get('stocks',[]):
                    if s and s[0] and s[0].get('stock') is not None:
                        qty = s[0].get('stock', 0)
                adjustments.append({"inventoryItemId": iid, "availableQuantity": int(qty)})
        logging.info(f"Toplam {len(adjustments)} stok ayarlaması hazırlandı.")
        return adjustments

    def _sync_variants_and_stock(self, product_gid, sentos_product):
        changes = []
        logging.info("Varyantlar ve stoklar senkronize ediliyor...")
        ex_vars = self._get_product_variants(product_gid)
        ex_skus = {str(v.get('inventoryItem',{}).get('sku','')).strip() for v in ex_vars if v.get('inventoryItem',{}).get('sku')}
        s_vars = sentos_product.get('variants', []) or [sentos_product]
        new_vars = [v for v in s_vars if str(v.get('sku','')).strip() not in ex_skus]
        if new_vars:
            msg = f"{len(new_vars)} yeni varyant eklendi."
            logging.info(msg)
            changes.append(msg)
            self._add_variants_to_product(product_gid, new_vars, sentos_product)
            time.sleep(3)
        all_now_variants = self._get_product_variants(product_gid)
        if adjustments := self._prepare_inventory_adjustments(s_vars, all_now_variants):
            msg = f"{len(adjustments)} varyantın stok seviyesi güncellendi."
            changes.append(msg)
            self._adjust_inventory_bulk(adjustments)
        if not new_vars and not adjustments:
            changes.append("Stok ve varyantlar kontrol edildi (Değişiklik yok).")
        logging.info("✅ Varyant ve stok senkronizasyonu tamamlandı.")
        return changes

    def create_new_product(self, sentos_product):
        changes = []
        product_name = sentos_product.get('name', 'Bilinmeyen Ürün')
        logging.info(f"Yeni ürün oluşturuluyor: '{product_name}'")
        try:
            product_input = self._prepare_basic_product_input(sentos_product)
            create_q = "mutation productCreate($input:ProductInput!){productCreate(input:$input){product{id} userErrors{field message}}}"
            created_product_data = self.shopify.execute_graphql(create_q, {'input': product_input}).get('productCreate', {})
            if not created_product_data.get('product'):
                errors = created_product_data.get('userErrors', [])
                raise Exception(f"Ürün oluşturulamadı: {errors}")
            product_gid = created_product_data['product']['id']
            sentos_variants = sentos_product.get('variants', []) or [sentos_product]
            variants_input = [self._prepare_variant_bulk_input(v, sentos_product, c=True) for v in sentos_variants]
            bulk_q = """
            mutation pVB($pId:ID!,$v:[ProductVariantsBulkInput!]!){
                productVariantsBulkCreate(productId:$pId,variants:$v,strategy:REMOVE_STANDALONE_VARIANT){
                    productVariants{id inventoryItem{id sku}} userErrors{field message}
                }
            }"""
            created_vars_data = self.shopify.execute_graphql(bulk_q, {'pId': product_gid, 'v': variants_input}).get('productVariantsBulkCreate', {})
            created_vars = created_vars_data.get('productVariants', [])
            changes.append(f"{len(created_vars)} varyantla oluşturuldu.")
            if adjustments := self._prepare_inventory_adjustments(sentos_variants, created_vars):
                changes.append(f"{len(adjustments)} varyantın stoğu ayarlandı.")
                self._adjust_inventory_bulk(adjustments)
            self._sync_product_options(product_gid, sentos_product)
            changes.extend(self._sync_product_media(product_gid, sentos_product, set_alt_text=True))
            logging.info(f"✅ Ürün başarıyla oluşturuldu: '{product_name}'")
            return changes
        except Exception as e:
            logging.error(f"Ürün oluşturma hatası: {e}"); raise

    def update_existing_product(self, sentos_product, existing_product, sync_mode):
        product_name = sentos_product.get('name', 'Bilinmeyen Ürün') 
        shopify_gid = existing_product['gid']
        logging.info(f"Mevcut ürün güncelleniyor: '{product_name}' (GID: {shopify_gid}) | Mod: {sync_mode}")
        all_changes = []
        try:
            if sync_mode in ["Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)", "Sadece Açıklamalar"]:
                 all_changes.extend(self._sync_core_details(shopify_gid, sentos_product))
            if sync_mode in ["Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)", "Sadece Kategoriler (Ürün Tipi)"]:
                all_changes.extend(self._sync_product_type(shopify_gid, sentos_product))
            if sync_mode in ["Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)", "Sadece Stok ve Varyantlar"]:
                all_changes.extend(self._sync_variants_and_stock(shopify_gid, sentos_product))
                self._sync_product_options(shopify_gid, sentos_product)
            if sync_mode == "Sadece Resimler":
                all_changes.extend(self._sync_product_media(shopify_gid, sentos_product, set_alt_text=False))
            if sync_mode in ["SEO Alt Metinli Resimler", "Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)"]:
                 all_changes.extend(self._sync_product_media(shopify_gid, sentos_product, set_alt_text=True))
            logging.info(f"✅ Ürün '{product_name}' başarıyla güncellendi.")
            return all_changes
        except Exception as e:
            logging.error(f"Ürün güncelleme hatası: {e}"); raise

    def _add_variants_to_product(self, product_gid, new_variants, main_product):
        v_in = [self._prepare_variant_bulk_input(v, main_product, c=True) for v in new_variants]
        bulk_q="""mutation pVBC($pId:ID!,$v:[ProductVariantsBulkInput!]!){productVariantsBulkCreate(productId:$pId,variants:$v){productVariants{id inventoryItem{id sku}} userErrors{field message}}}"""
        res=self.shopify.execute_graphql(bulk_q,{"pId":product_gid,"v":v_in})
        created=res.get('productVariantsBulkCreate',{}).get('productVariants',[])
        if errs:=res.get('productVariantsBulkCreate',{}).get('userErrors',[]): logging.error(f"Varyant ekleme hataları: {errs}")
        if created:self._activate_variants_at_location(created)
        return created

    def _activate_variants_at_location(self, variants):
        iids=[v['inventoryItem']['id'] for v in variants if v.get('inventoryItem',{}).get('id')]
        if not iids: return
        self.shopify.get_default_location_id()
        act_q="""mutation inventoryBulkToggleActivation($inventoryItemUpdates: [InventoryBulkToggleActivationInput!]!) {
            inventoryBulkToggleActivation(inventoryItemUpdates: $inventoryItemUpdates) {
                inventoryLevels { id }
                userErrors { field message }
            }
        }"""
        upds=[{"inventoryItemId":iid,"locationId":self.shopify.location_id,"activate":True} for iid in iids]
        try:
            self.shopify.execute_graphql(act_q,{"inventoryItemUpdates":upds})
        except Exception as e:
            logging.error(f"Inventory aktivasyon hatası: {e}")
    
    def _adjust_inventory_bulk(self, inventory_adjustments):
        if not inventory_adjustments: return
        location_id = self.shopify.get_default_location_id()
        mutation = """
        mutation inventorySetOnHandQuantities($input: InventorySetOnHandQuantitiesInput!) {
          inventorySetOnHandQuantities(input: $input) {
            userErrors { field message code }
          }
        }
        """
        variables = { "input": { "reason": "correction", "setQuantities": [ { "inventoryItemId": adj["inventoryItemId"], "quantity": adj["availableQuantity"], "locationId": location_id } for adj in inventory_adjustments ] } }
        try:
            self.shopify.execute_graphql(mutation, variables)
        except Exception as e:
            logging.error(f"Toplu stok güncelleme sırasında kritik bir hata oluştu: {e}")

    def sync_single_product(self, sentos_product, sync_mode, progress_callback):
        name = sentos_product.get('name', 'Bilinmeyen Ürün')
        sku = sentos_product.get('sku', 'SKU Yok')
        log_entry = {'name': name, 'sku': sku}
        try:
            if not name.strip():
                with self._lock: self.stats['skipped'] += 1
                return
            existing_product = self.find_shopify_product(sentos_product)
            changes_made = []
            if existing_product:
                changes_made = self.update_existing_product(sentos_product, existing_product, sync_mode)
                status, status_icon = 'updated', "🔄"
                with self._lock: self.stats['updated'] += 1
            elif sync_mode == "Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)":
                changes_made = self.create_new_product(sentos_product)
                status, status_icon = 'created', "✅"
                with self._lock: self.stats['created'] += 1
            else:
                with self._lock: self.stats['skipped'] += 1
                self.details.append({**log_entry, 'status': 'skipped', 'reason': 'Product not found in Shopify'})
                return
            changes_html = "".join([f'<li><small>{change}</small></li>' for change in changes_made])
            log_html = f"""
            <div style='border-bottom: 1px solid #444; padding-bottom: 8px; margin-bottom: 8px;'>
                <strong>{status_icon} {status.capitalize()}:</strong> {name} (SKU: {sku})
                <ul style='margin-top: 5px; margin-bottom: 0; padding-left: 20px;'>
                    {changes_html if changes_made else "<li><small>Değişiklik bulunamadı.</small></li>"}
                </ul>
            </div>
            """
            progress_callback({'log_detail': log_html})
            with self._lock: self.details.append(log_entry)
        except Exception as e:
            error_message = f"❌ Hata: {name} (SKU: {sku}) - {e}"
            progress_callback({'log_detail': f"<div style='color: #f48a94;'>{error_message}</div>"})
            with self._lock: 
                self.stats['failed'] += 1
                log_entry.update({'status': 'failed', 'reason': str(e)})
                self.details.append(log_entry)
        finally:
            with self._lock: self.stats['processed'] += 1

def sync_products_from_sentos_api(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, test_mode, progress_callback, stop_event, max_workers=3, sync_mode="Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)"):
    start_time = time.monotonic()
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)
        progress_callback({'message': "Shopify ürünleri arka planda önbelleğe alınıyor...", 'progress': 5})
        shopify_load_thread = threading.Thread(target=shopify_api.load_all_products, args=(progress_callback,))
        shopify_load_thread.start()
        progress_callback({'message': "Sentos'tan ürünler çekiliyor...", 'progress': 15})
        sentos_products = sentos_api.get_all_products(progress_callback=progress_callback)
        if test_mode: sentos_products = sentos_products[:20]
        logging.info("Ana işlem, Shopify önbelleğinin tamamlanmasını bekliyor...")
        shopify_load_thread.join()
        logging.info("Shopify önbelleği hazır. Ana işlem devam ediyor.")
        progress_callback({'message': f"{len(sentos_products)} ürün senkronize ediliyor...", 'progress': 55})
        sync_manager.stats['total'] = len(sentos_products)
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SyncWorker") as executor:
            futures = [executor.submit(sync_manager.sync_single_product, p, sync_mode, progress_callback) for p in sentos_products]
            for future in as_completed(futures):
                if stop_event.is_set(): 
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                processed = sync_manager.stats['processed']
                total = len(sentos_products)
                progress = 55 + int((processed / total) * 45) if total > 0 else 100
                progress_callback({'progress': progress, 'message': f"İşlenen: {processed}/{total}", 'stats': sync_manager.stats.copy()})
        duration = time.monotonic() - start_time
        results = {'stats': sync_manager.stats, 'details': sync_manager.details, 'duration': str(timedelta(seconds=duration))}
        progress_callback({'status': 'done', 'results': results})
    except Exception as e:
        logging.critical(f"Senkronizasyon görevi kritik bir hata oluştu: {e}\n{traceback.format_exc()}")
        progress_callback({'status': 'error', 'message': str(e)})
        raise 

def sync_single_product_by_sku(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, sku):
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)
        sentos_product = sentos_api.get_product_by_sku(sku)
        if not sentos_product:
            return {'success': False, 'message': f"'{sku}' SKU'su ile Sentos'ta ürün bulunamadı."}
        shopify_api.load_all_products()
        existing_product = sync_manager.find_shopify_product(sentos_product)
        if not existing_product:
            return {'success': False, 'message': f"'{sku}' SKU'su ile Shopify'da eşleşen ürün bulunamadı."}
        changes_made = sync_manager.update_existing_product(
            sentos_product, existing_product, "Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)"
        )
        product_name = sentos_product.get('name', sku)
        return {'success': True, 'product_name': product_name, 'changes': changes_made}
    except Exception as e:
        logging.error(f"Tekil ürün {sku} senkronizasyonunda hata: {e}\n{traceback.format_exc()}")
        return {'success': False, 'message': str(e)}

def sync_missing_products_only(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, test_mode, progress_callback, stop_event, max_workers):
    start_time = time.monotonic()
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)
        progress_callback({'message': "Shopify ürünleri arka planda önbelleğe alınıyor...", 'progress': 5})
        shopify_load_thread = threading.Thread(target=shopify_api.load_all_products, args=(progress_callback,))
        shopify_load_thread.start()
        progress_callback({'message': "Sentos'tan ürünler taranıyor...", 'progress': 15})
        sentos_products = sentos_api.get_all_products(progress_callback=progress_callback)
        if test_mode: sentos_products = sentos_products[:20]
        logging.info("Shopify önbelleğinin tamamlanması bekleniyor...")
        shopify_load_thread.join()
        logging.info("Eksik ürünler tespit ediliyor...")
        products_to_create = []
        for p in sentos_products:
            if not sync_manager.find_shopify_product(p):
                products_to_create.append(p)
        logging.info(f"{len(products_to_create)} adet eksik ürün bulundu.")
        progress_callback({'message': f"{len(products_to_create)} eksik ürün oluşturulacak...", 'progress': 55})
        sync_manager.stats['total'] = len(products_to_create)
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="CreateMissing") as executor:
            futures = [executor.submit(sync_manager.sync_single_product, p, "Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)", progress_callback) for p in products_to_create]
            for future in as_completed(futures):
                if stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                processed = sync_manager.stats['processed']
                total = len(products_to_create)
                progress = 55 + int((processed / total) * 45) if total > 0 else 100
                progress_callback({'progress': progress, 'message': f"Oluşturulan: {processed}/{total}", 'stats': sync_manager.stats.copy()})
        duration = time.monotonic() - start_time
        results = {'stats': sync_manager.stats, 'details': sync_manager.details, 'duration': str(timedelta(seconds=duration))}
        progress_callback({'status': 'done', 'results': results})
    except Exception as e:
        logging.critical(f"Eksik ürün senkronizasyonunda kritik hata: {e}\n{traceback.format_exc()}")
        progress_callback({'status': 'error', 'message': str(e)})

def run_sync_for_cron(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, sync_mode, max_workers):
    logging.info(f"Cron job başlatıldı. Mod: {sync_mode}")
    def cron_progress_callback(update):
        if 'message' in update:
            logging.info(update['message'])
        if 'log_detail' in update:
            clean_log = re.sub('<[^<]+?>', '', update['log_detail'])
            logging.info(clean_log)

    stop_event = threading.Event()
    
    sync_products_from_sentos_api(
        store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret,
        sentos_cookie, test_mode=False, progress_callback=cron_progress_callback,
        stop_event=stop_event, max_workers=max_workers, sync_mode=sync_mode
    )