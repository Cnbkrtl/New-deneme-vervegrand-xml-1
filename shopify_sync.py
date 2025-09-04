# shopify_sync.py

"""
Sentos API'den Shopify'a Ürün Senkronizasyonu Mantık Dosyası
Versiyon 22.1: Kararlı Başlatma ve Bellek Optimizasyonu
- YAPI: Senkronizasyonun başlangıcındaki ani bellek (RAM) patlamasını önlemek için
  ana senkronizasyon fonksiyonu yeniden tasarlandı.
- GÜNCELLEME: Shopify ürünleri önce tek başına yüklenir, ardından Sentos ürünleri
  sayfa sayfa (batch) işlenir. Bu, kaynak limitli platformlarda kararlı çalışmayı garantiler.
- KORUMA: Kullanıcının paylaştığı detaylı senkronizasyon ve loglama mantığı korunmuştur.
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
        self.rest_base_url = f"{self.store_url}/admin/api/2024-04"
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
            'User-Agent': 'Sentos-Sync-Python/22.1-Stable-Start'
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

    def load_all_products(self, progress_callback=None):
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

# --- Sentos API Sınıfı ---
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

    def get_products_by_page(self, page=1, page_size=50):
        """Sentos'tan ürünleri sayfa sayfa çeker."""
        endpoint = f"/products?page={page}&size={page_size}"
        try:
            response = self._make_request("GET", endpoint).json()
            return response
        except Exception as e:
            logging.error(f"Sentos'tan sayfa {page} çekilirken hata: {e}")
            raise

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
        """Sentos'ta SKU'ya göre tek bir ürün getirir."""
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

# --- Senkronizasyon Yöneticisi ---
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
        if not isinstance(size_str, str):
            return (3, 9999, size_str)

        size_upper = size_str.strip().upper()
        size_order_map = {
            'XXS': 0, 'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5,
            'XXL': 6, '2XL': 6, '3XL': 7, 'XXXL': 7,
            '4XL': 8, 'XXXXL': 8, '5XL': 9, 'XXXXXL': 9,
            'TEK EBAT': 100, 'STANDART': 100
        }
        if size_upper in size_order_map:
            return (1, size_order_map[size_upper], size_str)

        numbers = re.findall(r'\d+', size_str)
        if numbers:
            return (2, int(numbers[0]), size_str)

        return (3, 9999, size_str)

    def _prepare_basic_product_input(self, p):
        i = {"title": p.get('name','').strip(),"descriptionHtml":p.get('description_detail')or p.get('description',''),"vendor":"Vervegrand","status":"ACTIVE"}
        if cat:=p.get('category'): i['productType']=str(cat)
        i['tags'] = sorted(list({'Vervegrand', str(p.get('category'))} if p.get('category') else {'Vervegrand'}))
        
        v = p.get('variants',[]) or [p]
        c = sorted(list(set(self._get_variant_color(x) for x in v if self._get_variant_color(x))))
        
        unique_sizes = list(set(self._get_variant_size(x) for x in v if self._get_variant_size(x)))
        s = sorted(unique_sizes, key=self._get_apparel_sort_key)
        logging.info(f"Sentos Bedenleri: {unique_sizes} -> Sıralı: {s}")
        
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
        sizes = sorted(unique_sizes, key=self._get_apparel_sort_key)
        logging.info(f"Güncelleme için Sentos Bedenleri: {unique_sizes} -> Sıralı: {sizes}")
        
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
            
    def _add_new_media_to_product(self, product_gid, urls_to_add, product_title, set_alt_text=False):
        if not urls_to_add: return
        logging.info(f"Ürün GID: {product_gid} için {len(urls_to_add)} yeni medya eklenecek.")
        
        media_input = []
        for url in urls_to_add:
            alt_text = product_title if set_alt_text else url
            media_input.append({"originalSource": url, "alt": alt_text, "mediaContentType": "IMAGE"})

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

    def _sync_product_media(self, product_gid, sentos_product, set_alt_text=False):
        changes = []
        logging.info(f"Ürün {product_gid} için medya senkronizasyonu başlatılıyor...")
        product_title = sentos_product.get('name', '').strip()
        
        sentos_ordered_urls = self.sentos.get_ordered_image_urls(sentos_product.get('id'))
        
        if sentos_ordered_urls is None:
             logging.warning(f"Cookie eksik veya geçersiz, resim sırası alınamadı. Medya senkronizasyonu atlanıyor.")
             changes.append("Medya senkronizasyonu atlandı (Cookie eksik).")
             return changes

        if not sentos_ordered_urls:
            logging.info("Sentos'ta medya yok. Mevcut Shopify medyası siliniyor...")
            initial_shopify_media = self.shopify._get_product_media_details(product_gid)
            if media_ids_to_delete := [m['id'] for m in initial_shopify_media]:
                self.shopify.delete_product_media(product_gid, media_ids_to_delete)
                changes.append(f"{len(media_ids_to_delete)} Shopify görseli silindi.")
            return changes

        initial_shopify_media = self.shopify._get_product_media_details(product_gid)
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
            logging.info("Medya değişiklikleri sonrası 10 saniye bekleniyor...")
            time.sleep(10)
            final_shopify_media = self.shopify._get_product_media_details(product_gid)
            final_src_map = {m['originalSrc']: m['id'] for m in final_shopify_media if m.get('originalSrc')}
            ordered_media_ids = [final_src_map.get(url) for url in sentos_ordered_urls if final_src_map.get(url)]
            self.shopify.reorder_product_media(product_gid, ordered_media_ids)
        else:
            logging.info("Medya güncel, sıralama ve bekleme atlandı.")
        
        return changes

    def _get_variant_size(self, variant):
        model = variant.get('model', "")
        return (model.get('value', "") if isinstance(model, dict) else str(model)).strip() or None

    def _get_variant_color(self, variant):
        return (variant.get('color') or "").strip() or None

    def _sync_core_details(self, product_gid, sentos_product):
        changes = []
        logging.info("Temel ürün detayları güncelleniyor...")
        input_data = {
            "id": product_gid,
            "title": sentos_product.get('name', '').strip(),
            "descriptionHtml": sentos_product.get('description_detail') or sentos_product.get('description', '')
        }
        query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
        self.shopify.execute_graphql(query, {'input': input_data})
        changes.append("Başlık ve açıklama güncellendi.")
        logging.info("✅ Temel ürün detayları güncellendi.")
        return changes

    def _sync_product_type(self, product_gid, sentos_product):
        changes = []
        logging.info("Ürün kategorisi (productType) güncelleniyor...")
        if category := sentos_product.get('category'):
            input_data = {"id": product_gid, "productType": str(category)}
            query = "mutation pU($input:ProductInput!){productUpdate(input:$input){product{id} userErrors{field message}}}"
            self.shopify.execute_graphql(query, {'input': input_data})
            changes.append(f"Kategori '{category}' olarak ayarlandı.")
            logging.info(f"✅ Ürün kategorisi '{category}' olarak ayarlandı.")
        return changes
    
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
            
            msg = f"{len(created_vars)} varyantla oluşturuldu."
            changes.append(msg)
            logging.info(f"Aşama 2 tamamlandı. {msg}")
            
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
            if sync_mode in ["Full Sync (Create & Update All)", "Descriptions Only"]:
                 all_changes.extend(self._sync_core_details(shopify_gid, sentos_product))

            if sync_mode in ["Full Sync (Create & Update All)", "Categories (Product Type) Only"]:
                all_changes.extend(self._sync_product_type(shopify_gid, sentos_product))
            
            if sync_mode in ["Full Sync (Create & Update All)", "Stock & Variants Only"]:
                all_changes.extend(self._sync_variants_and_stock(shopify_gid, sentos_product))
                self._sync_product_options(shopify_gid, sentos_product)

            if sync_mode == "Images Only":
                all_changes.extend(self._sync_product_media(shopify_gid, sentos_product, set_alt_text=False))
            
            if sync_mode in ["Images with SEO Alt Text", "Full Sync (Create & Update All)"]:
                 all_changes.extend(self._sync_product_media(shopify_gid, sentos_product, set_alt_text=True))

            logging.info(f"✅ Ürün '{product_name}' başarıyla güncellendi.")
            return all_changes
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

    def sync_single_product(self, sentos_product, sync_mode, progress_callback):
        name = sentos_product.get('name', 'Bilinmeyen Ürün')
        sku = sentos_product.get('sku', 'SKU Yok')
        log_entry = {'name': name, 'sku': sku}
        
        try:
            if not name.strip():
                logging.warning(f"İsimsiz ürün atlandı (SKU: {sku})")
                with self._lock: self.stats['skipped'] += 1
                return

            existing_product = self.find_shopify_product(sentos_product)
            changes_made = []

            if existing_product:
                changes_made = self.update_existing_product(sentos_product, existing_product, sync_mode)
                status = 'updated'
                status_icon = "🔄"
                
                with self._lock: 
                    self.stats['updated'] += 1
                    log_entry['status'] = status
            
            elif sync_mode == "Full Sync (Create & Update All)":
                changes_made = self.create_new_product(sentos_product)
                status = 'created'
                status_icon = "✅"
                
                with self._lock: 
                    self.stats['created'] += 1
                    log_entry['status'] = status
            else:
                logging.warning(f"Ürün Shopify'da bulunamadı, atlanıyor (Mod: {sync_mode}, SKU: {sku})")
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
            
            with self._lock:
                self.details.append(log_entry)

        except Exception as e:
            error_message = f"❌ Hata: {name} (SKU: {sku}) - {e}"
            logging.error(f"{error_message}\n{traceback.format_exc()}")
            progress_callback({'log_detail': f"<div style='color: #f48a94;'>{error_message}</div>"})
            with self._lock: 
                self.stats['failed'] += 1
                log_entry.update({'status': 'failed', 'reason': str(e)})
                self.details.append(log_entry)
        finally:
            with self._lock: 
                self.stats['processed'] += 1

def _process_sentos_products_in_batches(sync_manager, sentos_api, sync_mode, progress_callback, stop_event, max_workers, test_mode=False):
    page = 1
    page_size = 20 if test_mode else 50
    
    while not stop_event.is_set():
        progress_callback({'message': f"Sentos'tan {page}. sayfa ürünler çekiliyor..."})
        
        response = sentos_api.get_products_by_page(page=page, page_size=page_size)
        products_on_page = response.get('data', [])
        
        if sync_manager.stats['total'] == 0:
            total_products = response.get('total_elements', 0)
            sync_manager.stats['total'] = min(total_products, page_size) if test_mode else total_products

        if not products_on_page:
            logging.info("Sentos'tan çekilecek başka ürün kalmadı. Senkronizasyon tamamlanıyor.")
            break

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SyncWorker") as executor:
            futures = [executor.submit(sync_manager.sync_single_product, p, sync_mode, progress_callback) for p in products_on_page]
            for future in as_completed(futures):
                if stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    logging.warning("Durdurma sinyali alındı, mevcut sayfa işlenmesi durduruluyor.")
                    return
                
                processed = sync_manager.stats['processed']
                total = sync_manager.stats['total']
                progress = int((processed / total) * 100) if total > 0 else 0
                progress_callback({'progress': progress, 'message': f"İşlenen: {processed}/{total}", 'stats': sync_manager.stats.copy()})
        
        if test_mode:
            logging.info("Test modu aktif, sadece ilk sayfa işlendi.")
            break

        page += 1
        time.sleep(1)

def sync_products_from_sentos_api(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, test_mode, progress_callback, stop_event, max_workers=3, sync_mode="Full Sync (Create & Update All)"):
    start_time = time.monotonic()
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)

        progress_callback({'message': "Shopify ürünleri önbelleğe alınıyor...", 'progress': 10})
        shopify_api.load_all_products(progress_callback=progress_callback)
        
        if stop_event.is_set():
            raise Exception("İşlem başlangıçta durduruldu.")

        progress_callback({'message': "Sentos ürünleri işlenmeye başlıyor...", 'progress': 40})
        _process_sentos_products_in_batches(
            sync_manager, sentos_api, sync_mode, progress_callback, stop_event, max_workers, test_mode
        )

        duration = time.monotonic() - start_time
        results = {
            'stats': sync_manager.stats, 
            'details': sync_manager.details,
            'duration': str(timedelta(seconds=duration))
        }
        progress_callback({'status': 'done', 'results': results, 'progress': 100})
        logging.info(f"Senkronizasyon {results['duration']} sürede tamamlandı. Sonuçlar: {results['stats']}")

    except Exception as e:
        logging.critical(f"Senkronizasyon görevi başlatılamadı veya kritik bir hata oluştu: {e}\n{traceback.format_exc()}")
        progress_callback({'status': 'error', 'message': str(e)})

def run_sync_for_cron(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, sync_mode="Stock & Variants Only", max_workers=2):
    """
    Bu fonksiyon, RQ worker veya zamanlanmış görevler (örn: GitHub Actions) tarafından
    çalıştırılmak üzere tasarlanmıştır. Arayüz geri bildirimi (progress_callback)
    ve durdurma olayı (stop_event) için sahte (dummy) versiyonlar oluşturur.
    """
    logging.info(f"Zamanlanmış görev (cron) senkronizasyonu başlatılıyor... Mod: {sync_mode}")
    
    # Arayüze özel callback'lerin loglama yapan sahte versiyonları
    def cron_progress_callback(data):
        if message := data.get('message'):
            logging.info(f"[CRON-PROGRESS] {message}")
        if stats := data.get('stats'):
            logging.info(f"[CRON-STATS] {stats}")
    
    # Sahte durdurma olayı
    dummy_stop_event = threading.Event()

    try:
        # Ana senkronizasyon fonksiyonunu çağır
        sync_products_from_sentos_api(
            store_url=store_url,
            access_token=access_token,
            sentos_api_url=sentos_api_url,
            sentos_api_key=sentos_api_key,
            sentos_api_secret=sentos_api_secret,
            sentos_cookie=sentos_cookie,
            test_mode=False, # Cron job'lar asla test modunda çalışmaz
            progress_callback=cron_progress_callback,
            stop_event=dummy_stop_event,
            max_workers=max_workers,
            sync_mode=sync_mode
        )
        logging.info("Zamanlanmış senkronizasyon görevi başarıyla tamamlandı.")
    except Exception as e:
        logging.error(f"Zamanlanmış senkronizasyon görevinde kritik hata: {e}", exc_info=True)

def sync_missing_products_only(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, test_mode, progress_callback, stop_event, max_workers):
    """
    Sentos'ta olup Shopify'da olmayan ürünleri bulur ve sadece onları oluşturur.
    Mevcut ürünlere dokunmaz.
    """
    start_time = time.monotonic()
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)

        progress_callback({'message': "Mevcut Shopify ürünleri önbelleğe alınıyor...", 'progress': 10})
        shopify_api.load_all_products(progress_callback=progress_callback)
        
        if stop_event.is_set(): raise Exception("İşlem başlangıçta durduruldu.")

        page = 1
        page_size = 20 if test_mode else 50
        products_to_create = []

        # 1. Aşama: Eksik ürünleri bulma
        progress_callback({'message': "Sentos ürünleri taranıyor ve eksikler bulunuyor...", 'progress': 40})
        while not stop_event.is_set():
            response = sentos_api.get_products_by_page(page=page, page_size=page_size)
            products_on_page = response.get('data', [])
            if not products_on_page: break
            
            for p in products_on_page:
                if not sync_manager.find_shopify_product(p):
                    products_to_create.append(p)
            
            if test_mode: break
            page += 1
        
        sync_manager.stats['total'] = len(products_to_create)
        logging.info(f"Shopify'da eksik olan {len(products_to_create)} ürün bulundu ve oluşturulacak.")

        # 2. Aşama: Bulunan eksik ürünleri oluşturma
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="CreateMissing") as executor:
            futures = {executor.submit(sync_manager.create_new_product, p): p for p in products_to_create}
            for future in as_completed(futures):
                if stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                
                sentos_product = futures[future]
                try:
                    changes = future.result()
                    status_icon, status = "✅", "created"
                    sync_manager.stats['created'] += 1
                    html_log = f"<div><strong>{status_icon} Oluşturuldu:</strong> {sentos_product.get('name')}</div>"
                    progress_callback({'log_detail': html_log})
                except Exception as e:
                    sync_manager.stats['failed'] += 1
                    error_message = f"❌ Hata: {sentos_product.get('name')} oluşturulamadı - {e}"
                    progress_callback({'log_detail': f"<div style='color: #f48a94;'>{error_message}</div>"})
                
                sync_manager.stats['processed'] += 1
                processed = sync_manager.stats['processed']
                total = sync_manager.stats['total']
                progress = int((processed / total) * 100) if total > 0 else 0
                progress_callback({'progress': progress, 'message': f"Oluşturulan: {processed}/{total}", 'stats': sync_manager.stats.copy()})

        duration = time.monotonic() - start_time
        results = {'stats': sync_manager.stats, 'details': sync_manager.details, 'duration': str(timedelta(seconds=duration))}
        progress_callback({'status': 'done', 'results': results, 'progress': 100})

    except Exception as e:
        logging.critical(f"Eksik ürün senkronizasyonunda hata: {e}\n{traceback.format_exc()}")
        progress_callback({'status': 'error', 'message': str(e)})


# --- YENİ ÖZELLİK 2: SKU İLE TEKİL ÜRÜN GÜNCELLEME FONKSİYONU ---
def sync_single_product_by_sku(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie, sku):
    """
    Verilen SKU'yu Sentos'ta bulur ve Shopify'daki karşılığını tam olarak günceller.
    """
    try:
        shopify_api = ShopifyAPI(store_url, access_token)
        sentos_api = SentosAPI(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
        sync_manager = ProductSyncManager(shopify_api, sentos_api)

        # 1. Sentos'tan ürünü bul
        sentos_product = sentos_api.get_product_by_sku(sku)
        if not sentos_product:
            return {'success': False, 'message': f"'{sku}' SKU'su ile Sentos'ta ürün bulunamadı."}

        # 2. Shopify'da karşılığını bulmak için önbelleği yükle
        shopify_api.load_all_products()
        
        existing_product = sync_manager.find_shopify_product(sentos_product)
        if not existing_product:
            return {'success': False, 'message': f"'{sku}' SKU'su ile Shopify'da eşleşen ürün bulunamadı. Lütfen önce oluşturun."}

        # 3. Ürünü tam güncelleme modunda senkronize et
        changes_made = sync_manager.update_existing_product(sentos_product, existing_product, "Full Sync (Create & Update All)")

        message = f"'{sentos_product.get('name')}' ürünü başarıyla güncellendi. Yapılan Değişiklikler: {', '.join(changes_made) or 'Değişiklik yok.'}"
        return {'success': True, 'message': message}

    except Exception as e:
        logging.error(f"Tekil ürün {sku} senkronizasyonunda hata: {e}\n{traceback.format_exc()}")
        return {'success': False, 'message': str(e)}        