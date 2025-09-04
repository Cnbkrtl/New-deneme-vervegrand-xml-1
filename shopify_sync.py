"""
Sentos API'den Shopify'a Ürün Senkronizasyonu Mantık Dosyası
Versiyon 20.0: RQ Entegrasyonu ve Worker İlerleme Raporlama Düzeltmesi
- GÜNCELLEME: Arka plan görevlerinin ilerlemesini arayüze bildirebilmesi için RQ'nun 'get_current_job' mekanizması entegre edildi.
- GÜNCELLEME: 'progress_callback' parametresi kaldırıldı, artık gereksiz.
- TEMİZLİK: Fonksiyon parametre isimleri (sentos_user_id -> sentos_api_secret) arayüz ile tutarlı hale getirildi.
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
from rq import get_current_job  # <-- GEREKLİ EKLEME

# --- Loglama Konfigürasyonu ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Shopify API Entegrasyon Sınıfı (Değişiklik yok) ---
class ShopifyAPI:
    def __init__(self, store_url, access_token):
        if not store_url: raise ValueError("Shopify Mağaza URL'si boş olamaz.")
        if not access_token: raise ValueError("Shopify Erişim Token'ı boş olamaz.")
        
        self.store_url = store_url if store_url.startswith('http') else f"https://{store_url.strip()}"
        self.access_token = access_token
        self.graphql_url = f"{self.store_url}/admin/api/2024-04/graphql.json"
        self.rest_base_url = f"{self.store_url}/admin/api/2024-04"
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
            'User-Agent': 'Sentos-Sync-Python/20.0-RQ-Fix'
        }
        self.product_cache = {}
        self.location_id = None

    def _make_request(self, method, endpoint, data=None, is_graphql=False):
        url = self.graphql_url if is_graphql else f"{self.rest_base_url}/{endpoint}"
        try:
            time.sleep(0.51)
            response = requests.request(method, url, headers=self.headers, json=data, timeout=90)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 10))
                logging.warning(f"Shopify API rate limit'e takıldı. {retry_after} saniye bekleniyor...")
                time.sleep(retry_after)
                return self._make_request(method, endpoint, data, is_graphql)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Shopify API Bağlantı Hatası ({url}): {e}")
            raise

    def execute_graphql(self, query, variables=None):
        payload = {'query': query, 'variables': variables or {}}
        response_data = self._make_request('POST', '', data=payload, is_graphql=True)
        
        if "errors" in response_data:
            error_messages = [err.get('message', 'Bilinmeyen GraphQL hatası') for err in response_data["errors"]]
            logging.error(f"GraphQL sorgusu hata verdi: {json.dumps(response_data['errors'], indent=2)}")
            raise Exception(f"GraphQL Error: {', '.join(error_messages)}")
        return response_data.get("data", {})
    
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

    def load_all_products(self, progress_callback=None): # Bu callback iç kullanım için kalabilir
        total_loaded = 0
        endpoint = f'{self.rest_base_url}/products.json?limit=250&fields=id,title,variants'
        
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
            endpoint = next((link['url'] for link in requests.utils.parse_header_links(response.headers.get('Link', '')) if link.get('rel') == 'next'), None)
        
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

# --- Sentos API Sınıfı (Değişiklik yok) ---
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
    
    def get_all_products(self, progress_callback=None, page_size=100): # Bu callback iç kullanım için kalabilir
        all_products, page = [], 1
        total_pages, total_elements = None, None
        
        while True:
            endpoint = f"/products?page={page}&size={page_size}"
            try:
                response = self._make_request("GET", endpoint).json()
                products_on_page = response.get('data', [])
                
                if not products_on_page and page > 1: break
                all_products.extend(products_on_page)
                
                if total_pages is None: total_pages = response.get('total_pages', '?')
                if total_elements is None: total_elements = response.get('total_elements', 'Bilinmiyor')

                if progress_callback:
                    progress_callback({'message': f"Sentos'tan ürünler çekiliyor (Sayfa: {page}/{total_pages})..."})
                
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

# --- Senkronizasyon Yöneticisi (Değişiklik yok) ---
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
    
    def _prepare_basic_product_input(self, p):
        i = {"title": p.get('name','').strip(),"descriptionHtml":p.get('description_detail')or p.get('description',''),"vendor":"Vervegrand","status":"ACTIVE"}
        if cat:=p.get('category'): i['productType']=str(cat)
        i['tags'] = sorted(list({'Vervegrand', str(p.get('category'))} if p.get('category') else {'Vervegrand'}))
        
        v = p.get('variants',[]) or [p]
        c = sorted(list(set(self._get_variant_color(x) for x in v if self._get_variant_color(x))))
        
        unique_sizes = list(set(self._get_variant_size(x) for x in v if self._get_variant_size(x)))
        logging.info(f"Sıralanmamış benzersiz bedenler: {unique_sizes}")

        def get_numerical_sort_key(size_str):
            if not isinstance(size_str, str): return (9999, size_str)
            numbers = re.findall(r'\d+', size_str)
            if numbers:
                return (int(numbers[0]), size_str)
            return (9999, size_str)

        s = sorted(unique_sizes, key=get_numerical_sort_key)
        logging.info(f"Sayısal olarak sıralanmış bedenler: {s}")
        
        o=[]
        if c:o.append({"name":"Renk","values":[{"name":x} for x in c]})
        if s:o.append({"name":"Beden","values":[{"name":x} for x in s]})
        if o:i['productOptions']=o
        return i

    def _sync_product_options(self, product_gid, sentos_product):
        logging.info(f"Ürün {product_gid} için seçenek sıralaması kontrol ediliyor...")
        v = sentos_product.get('variants', []) or [sentos_product]

        colors = sorted(list(set(self._get_variant_color(x) for x in v if self._get_variant_color(x))))
        
        unique_sizes = list(set(self._get_variant_size(x) for x in v if self._get_variant_size(x)))
        def get_numerical_sort_key(size_str):
            if not isinstance(size_str, str): return (9999, size_str)
            numbers = re.findall(r'\d+', size_str)
            if numbers: return (int(numbers[0]), size_str)
            return (9999, size_str)
        sizes = sorted(unique_sizes, key=get_numerical_sort_key)
        
        options_input = []
        if colors:
            options_input.append({"name": "Renk", "values": [{"name": c} for c in colors]})
        if sizes:
            options_input.append({"name": "Beden", "values": [{"name": s} for s in sizes]})
        
        if not options_input:
            logging.info("Yeniden sıralanacak seçenek bulunamadı.")
            return

        query = """
        mutation productOptionsReorder($productId: ID!, $options: [OptionReorderInput!]!) {
          productOptionsReorder(productId: $productId, options: $options) {
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {"productId": product_gid, "options": options_input}

        try:
            result = self.shopify.execute_graphql(query, variables)
            if errors := result.get('productOptionsReorder', {}).get('userErrors', []):
                logging.error(f"Seçenekler yeniden sıralanırken hata oluştu: {errors}")
            else:
                logging.info(f"✅ Ürün {product_gid} için seçenekler başarıyla yeniden sıralandı.")
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
            
    def _add_new_media_to_product(self, product_gid, urls_to_add):
        if not urls_to_add: return
        logging.info(f"Ürün GID: {product_gid} için {len(urls_to_add)} yeni medya eklenecek.")
        media_input = [{"originalSource": url, "alt": url, "mediaContentType": "IMAGE"} for url in urls_to_add]
        
        for i in range(0, len(media_input), 10):
            batch = media_input[i:i + 10]
            try:
                query = """
                mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
                    productCreateMedia(productId: $productId, media: $media) {
                        media { id }
                        mediaUserErrors { field message }
                    }
                }
                """
                result = self.shopify.execute_graphql(query, {'productId': product_gid, 'media': batch})
                if errors := result.get('productCreateMedia', {}).get('mediaUserErrors', []):
                    logging.warning(f"Medya ekleme hataları: {errors}")
            except Exception as e:
                logging.error(f"Medya batch {i//10 + 1} eklenirken hata: {e}")

    def _sync_product_media(self, product_gid, sentos_product):
        logging.info(f"Ürün {product_gid} için medya senkronizasyonu başlatılıyor...")
        
        sentos_ordered_urls = self.sentos.get_ordered_image_urls(sentos_product.get('id'))
        
        if sentos_ordered_urls is None:
             logging.warning(f"Cookie eksik veya geçersiz olduğu için ürün ID {sentos_product.get('id')} resim sırası alınamadı. Medya senkronizasyonu atlanıyor.")
             return

        if not sentos_ordered_urls:
            logging.info("Sentos ürününde medya bulunamadı. Mevcut Shopify medyası siliniyor (varsa)...")
            initial_shopify_media = self.shopify._get_product_media_details(product_gid)
            if media_ids_to_delete := [m['id'] for m in initial_shopify_media]:
                self.shopify.delete_product_media(product_gid, media_ids_to_delete)
            return

        initial_shopify_media = self.shopify._get_product_media_details(product_gid)
        shopify_alt_map = {m['alt']: m['id'] for m in initial_shopify_media if m.get('alt')}
        
        sentos_urls_set = set(sentos_ordered_urls)
        shopify_alts_set = set(shopify_alt_map.keys())
        
        urls_to_add = list(sentos_urls_set - shopify_alts_set)
        alts_to_delete = list(shopify_alts_set - sentos_urls_set)
        media_ids_to_delete = [shopify_alt_map[alt] for alt in alts_to_delete]
        
        media_changed = False
        if urls_to_add:
            self._add_new_media_to_product(product_gid, urls_to_add)
            media_changed = True
        if media_ids_to_delete:
            self.shopify.delete_product_media(product_gid, media_ids_to_delete)
            media_changed = True
        
        if media_changed:
            logging.info("Medya değişiklikleri sonrası Shopify'ın işlemesi için 10 saniye bekleniyor...")
            time.sleep(10) 

            final_shopify_media = self.shopify._get_product_media_details(product_gid)
            final_alt_map = {m['alt']: m['id'] for m in final_shopify_media if m.get('alt')}
            
            ordered_media_ids = [final_alt_map.get(url) for url in sentos_ordered_urls if final_alt_map.get(url)]
            
            if len(ordered_media_ids) >= len(sentos_ordered_urls):
                self.shopify.reorder_product_media(product_gid, ordered_media_ids)
            else:
                logging.warning(f"Sıralama atlandı: Tüm medyalar Shopify'da bulunamadı. Beklenen: {len(sentos_ordered_urls)}, Bulunan: {len(ordered_media_ids)}")
        else:
            logging.info("Medya güncel, sıralama ve bekleme atlandı.")

    def _get_variant_size(self, variant):
        model = variant.get('model', "")
        return (model.get('value', "") if isinstance(model, dict) else str(model)).strip() or None

    def _get_variant_color(self, variant):
        return (variant.get('color') or "").strip() or None

    def create_new_product(self, sentos_product):
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
            logging.info(f"Aşama 1 tamamlandı. Ürün GID: {product_gid}")
            
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
            logging.info(f"Aşama 2 tamamlandı. {len(created_vars)} varyant eklendi.")
            
            if adjustments := self._prepare_inventory_adjustments(sentos_variants, created_vars):
                self._adjust_inventory_bulk(adjustments)

            self._sync_product_options(product_gid, sentos_product)
            
            self._sync_product_media(product_gid, sentos_product)
            logging.info(f"✅ Ürün başarıyla oluşturuldu: '{product_name}'")
            return True
        except Exception as e:
            logging.error(f"Ürün oluşturma hatası: {e}"); raise

    def update_existing_product(self, sentos_product, existing_product):
        product_name = sentos_product.get('name', 'Bilinmeyen Ürün') 
        shopify_gid = existing_product['gid']
        logging.info(f"Mevcut ürün güncelleniyor: '{product_name}' (GID: {shopify_gid})")
        try:
            ex_vars = self._get_product_variants(shopify_gid)
            ex_skus = {str(v.get('inventoryItem',{}).get('sku','')).strip() for v in ex_vars if v.get('inventoryItem',{}).get('sku')}
            
            s_vars = sentos_product.get('variants', []) or [sentos_product]
            new_vars = [v for v in s_vars if str(v.get('sku','')).strip() not in ex_skus]
            
            if new_vars:
                logging.info(f"{len(new_vars)} yeni varyant ekleniyor...")
                self._add_variants_to_product(shopify_gid, new_vars, sentos_product)
            
            self._sync_product_options(shopify_gid, sentos_product)
            
            time.sleep(3)
            
            all_now_variants = self._get_product_variants(shopify_gid)
            if adjustments := self._prepare_inventory_adjustments(s_vars, all_now_variants):
                self._adjust_inventory_bulk(adjustments)
            
            self._sync_product_media(shopify_gid, sentos_product)
            logging.info("✅ Ürün başarıyla güncellendi")
            return True
        except Exception as e:
            logging.error(f"Ürün güncelleme hatası: {e}"); raise

    def _get_product_variants(self, product_gid):
        q="""query gPV($id:ID!){product(id:$id){variants(first:250){edges{node{id inventoryItem{id sku}}}}}}"""
        data=self.shopify.execute_graphql(q,{"id":product_gid})
        return [e['node'] for e in data.get("product",{}).get("variants",{}).get("edges",[])]

    def _add_variants_to_product(self, product_gid, new_variants, main_product):
        v_in = [self._prepare_variant_bulk_input(v, main_product, c=True) for v in new_variants]
        bulk_q="""mutation pVBC($pId:ID!,$v:[ProductVariantsBulkInput!]!){productVariantsBulkCreate(productId:$pId,variants:$v){productVariants{id inventoryItem{id sku}} userErrors{field message}}}"""
        res=self.shopify.execute_graphql(bulk_q,{"productId":product_gid,"variants":v_in})
        created=res.get('productVariantsBulkCreate',{}).get('productVariants',[])
        if errs:=res.get('productVariantsBulkCreate',{}).get('userErrors',[]): logging.error(f"Varyant ekleme hataları: {errs}")
        logging.info(f"{len(created)} yeni varyant eklendi")
        if created:self._activate_variants_at_location(created)
        return created

    def _activate_variants_at_location(self, variants):
        iids=[v['inventoryItem']['id'] for v in variants if v.get('inventoryItem',{}).get('id')]
        if not iids: return
        self.shopify.get_default_location_id()
        act_q="""mutation iBTA($iids:[ID!]!,$upds:[InventoryBulkToggleActivationInput!]!){inventoryBulkToggleActivation(inventoryItemIds:$iids,inventoryItemUpdates:$upds){inventoryLevels{id} userErrors{field message}}}"""
        upds=[{"inventoryItemId":iid,"locationId":self.shopify.location_id,"activate":True} for iid in iids]
        try:
            res=self.shopify.execute_graphql(act_q,{"inventoryItemIds":iids,"inventoryItemUpdates":upds})
            if errs:=res.get('inventoryBulkToggleActivation',{}).get('userErrors',[]): logging.error(f"Inventory aktivasyon hataları: {errs}")
            logging.info(f"{len(res.get('inventoryBulkToggleActivation',{}).get('inventoryLevels',[]))} inventory level aktive edildi")
        except Exception as e:
            logging.error(f"Inventory aktivasyon hatası: {e}")

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

    def _adjust_inventory_bulk(self, inventory_adjustments):
        if not inventory_adjustments:
            logging.info("Ayarlanacak stok bulunmuyor.")
            return

        location_id = self.shopify.get_default_location_id()
        logging.info(f"GraphQL ile {len(inventory_adjustments)} adet stok ayarlanıyor. Lokasyon: {location_id}")
        
        mutation = """
        mutation inventorySetOnHandQuantities($input: InventorySetOnHandQuantitiesInput!) {
          inventorySetOnHandQuantities(input: $input) {
            userErrors {
              field
              message
              code
            }
          }
        }
        """
        
        variables = {
            "input": {
                "reason": "correction",
                "setQuantities": [
                    {
                        "inventoryItemId": adj["inventoryItemId"],
                        "quantity": adj["availableQuantity"],
                        "locationId": location_id
                    }
                    for adj in inventory_adjustments
                ]
            }
        }

        try:
            response = self.shopify.execute_graphql(mutation, variables)
            data = response.get('inventorySetOnHandQuantities', {})
            if errors := data.get('userErrors', []):
                logging.error(f"Toplu stok güncelleme sırasında GraphQL hataları oluştu: {errors}")
            else:
                logging.info(f"✅ GraphQL ile {len(inventory_adjustments)} stok ayarlama isteği başarıyla gönderildi.")
        except Exception as e:
            logging.error(f"Toplu stok güncelleme sırasında kritik bir hata oluştu: {e}")

    def sync_single_product(self, sentos_product):
        name = sentos_product.get('name', 'Bilinmeyen Ürün')
        sku = sentos_product.get('sku', 'SKU Yok')
        log_detail = {'name': name, 'sku': sku}
        logging.info(f"--- Ürün işleniyor: '{name}' (SKU: {sku}) ---")
        try:
            if not name.strip():
                logging.warning(f"İsimsiz ürün atlandı (SKU: {sku})"); self.stats['skipped'] += 1; return
            if ex_prod := self.find_shopify_product(sentos_product):
                self.update_existing_product(sentos_product, ex_prod)
                with self._lock: self.stats['updated']+=1; self.details.append({**log_detail,'status':'updated'})
            else:
                self.create_new_product(sentos_product)
                with self._lock: self.stats['created']+=1; self.details.append({**log_detail,'status':'created'})
        except Exception as e:
            logging.error(f"❌ '{name}' ürünü işlenirken hata: {e}\n{traceback.format_exc()}")
            with self._lock: self.stats['failed']+=1; self.details.append({**log_detail,'status':'failed','reason':str(e)})
        finally:
            with self._lock: self.stats['processed'] += 1

# --- Ana Senkronizasyon Fonksiyonu ---
def sync_products_from_sentos_api(
    shopify_store, 
    shopify_token, 
    sentos_api_url, 
    sentos_api_key, 
    sentos_api_secret, 
    sentos_cookie,
    enable_detailed_logs=True, # 'test_mode' ile aynı işlevi görebilir veya ayrı mantık eklenebilir
    max_workers=10, 
    sync_mode="Full Sync"
    # progress_callback parametresi kaldırıldı
):
    """Ana sync fonksiyonu"""
    
    # Progress callback güvenli çağrı fonksiyonu
    def safe_progress_callback(data):
        # Arka plan görevinin meta verisini güncelle
        try:
            job = get_current_job()
            if job:
                # Gelen yeni veriyi mevcut meta verisiyle birleştir
                job.meta.update(data)
                job.save_meta()
        except Exception as e:
            logging.warning(f"RQ meta verisi güncellenirken hata oluştu: {e}")
    
    try:
        shopify_api = ShopifyAPI(shopify_store, shopify_token)
        # 'sentos_user_id' yerine 'sentos_api_secret' kullanılıyor, daha anlaşılır.
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)

        safe_progress_callback({'message': "Shopify ürünleri arka planda önbelleğe alınıyor...", 'progress': 5})
        shopify_api.load_all_products(progress_callback=safe_progress_callback)
        
        safe_progress_callback({'message': "Sentos'tan ürünler çekiliyor...", 'progress': 15})
        sentos_products = sentos_api.get_all_products(progress_callback=safe_progress_callback)
        
        if not sentos_products:
            return {'stats': {'message': 'Sentos\'ta senkronize edilecek ürün bulunamadı.'}, 'details': []}

        safe_progress_callback({'message': f"{len(sentos_products)} ürün senkronize ediliyor...", 'progress': 55})
        
        sync_manager = ProductSyncManager(shopify_api, sentos_api)
        sync_manager.stats['total'] = len(sentos_products)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(sync_manager.sync_single_product, p) for p in sentos_products]
            for future in as_completed(futures):
                processed = sync_manager.stats['processed']; total = len(sentos_products)
                progress = 55 + int((processed / total) * 45) if total > 0 else 100
                safe_progress_callback({'progress': progress, 'message': f"İşlenen: {processed}/{total}", 'stats': sync_manager.stats.copy()})
        
        safe_progress_callback({'status': 'done', 'results': {'stats': sync_manager.stats, 'details': sync_manager.details}})
        
        return {'stats': sync_manager.stats, 'details': sync_manager.details}
        
    except Exception as e:
        logging.critical(f"Senkronizasyon görevi kritik hata: {e}\n{traceback.format_exc()}")
        safe_progress_callback({'status': 'error', 'message': str(e)})
        raise