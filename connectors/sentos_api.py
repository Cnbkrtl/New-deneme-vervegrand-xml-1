# connectors/sentos_api.py - Eski çalışan koddan uyarlanmış

import requests
import time
import logging
import re
import json
from urllib.parse import urljoin, urlparse
from requests.auth import HTTPBasicAuth

class SentosAPI:
    """Sentos API ile iletişimi yöneten sınıf."""
    def __init__(self, api_url, api_key, api_secret, api_cookie=None):
        self.api_url = api_url.strip().rstrip('/')
        self.auth = HTTPBasicAuth(api_key, api_secret)
        self.api_cookie = api_cookie
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # Yeniden deneme ayarları
        self.max_retries = 3
        self.base_delay = 5  # saniye cinsinden

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

        for attempt in range(self.max_retries):
            try:
                response = requests.request(method, url, headers=headers, auth=auth, data=data, params=params, timeout=30)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                # 500 (Sunucu hatası) ve 429 (Too Many Requests) hatalarında tekrar dene
                if e.response.status_code in [500, 429] and attempt < self.max_retries - 1:
                    wait_time = self.base_delay * (2 ** attempt)  # Üstel geri çekilme
                    logging.warning(f"Sentos API'den 500 veya 429 hatası alındı. {wait_time} saniye beklenip tekrar denenecek... (Deneme {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    # Diğer hatalarda veya son denemede istisnayı yükselt
                    logging.error(f"Sentos API Hatası ({url}): {e}")
                    raise Exception(f"Sentos API Hatası ({url}): {e}")
            except requests.exceptions.RequestException as e:
                # Bağlantı ve diğer genel istek hatalarını yakala
                logging.error(f"Sentos API Bağlantı Hatası ({url}): {e}")
                raise Exception(f"Sentos API Bağlantı Hatası ({url}): {e}")
    
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
                    message = f"Sentos'tan ürünler çekiliyor ({len(all_products)} / {total_elements})... Geçen süre: {int(elapsed_time)}s"
                    progress = int((len(all_products) / total_elements) * 100) if isinstance(total_elements, int) and total_elements > 0 else 0
                    progress_callback({'message': message, 'progress': progress})
                
                if len(products_on_page) < page_size: break
                page += 1
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Sayfa {page} çekilirken hata: {e}")
                # Hata durumunda işlemi sonlandır. _make_request zaten tekrar denemeyi yönetiyor.
                raise Exception(f"Sentos API'den ürünler çekilemedi: {e}")
            
        logging.info(f"Sentos'tan toplam {len(all_products)} ürün çekildi.")
        return all_products

    def get_ordered_image_urls(self, product_id):
        """
        ESKİ KODDAN ALINMIŞ ÇALIŞAN VERSİYON
        Cookie eksikse None döner (bu kritik!)
        """
        if not self.api_cookie:
            logging.warning(f"Sentos Cookie ayarlanmadığı için sıralı resimler alınamıyor (Ürün ID: {product_id}).")
            return None  # ← Bu None dönmesi kritik!

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
                    # Orijinal regex pattern'i kullan
                    match = re.search(r'href="(https?://[^"]+/o_[^"]+)"', html_string)
                    if match:
                        ordered_urls.append(match.group(1))

            logging.info(f"Ürün ID {product_id} için {len(ordered_urls)} adet sıralı resim URL'si bulundu.")
            return ordered_urls
            
        except ValueError as ve:
            logging.error(f"Resim sırası alınamadı: {ve}")
            return None
        except Exception as e:
            logging.error(f"Sıralı resimler çekilirken hata oluştu (Ürün ID: {product_id}): {e}")
            return []  # Hata durumunda boş liste döner

    def get_product_by_sku(self, sku):
        """Verilen SKU'ya göre Sentos'tan tek bir ürün çeker."""
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
            # API liste döndürdüğü için ilk elemanı alıyoruz.
            return products[0]
        except Exception as e:
            logging.error(f"Sentos'ta SKU '{sku}' aranırken hata: {e}")
            raise

    def test_connection(self):
        try:
            response = self._make_request("GET", "/products?page=1&size=1").json()
            return {'success': True, 'total_products': response.get('total_elements', 0), 'message': 'REST API OK'}
        except Exception as e:
            return {'success': False, 'message': f'REST API failed: {e}'}

    def test_image_fetch_debug(self, product_id):
        """Debug amaçlı görsel çekme testi"""
        result = {
            "product_id": product_id,
            "cookie_available": bool(self.api_cookie),
            "cookie_length": len(self.api_cookie) if self.api_cookie else 0,
            "success": False,
            "images_found": [],
            "error": None
        }
        
        if not self.api_cookie:
            result["error"] = "Cookie mevcut değil"
            return result
        
        try:
            # Cookie preview (güvenlik için sadece başını göster)
            if self.api_cookie:
                logging.info(f"Cookie preview: {self.api_cookie[:50]}...")
            
            endpoint = "/urun_sayfalari/include/ajax/fetch_urunresimler.php"
            payload = {
                'draw': '1', 'start': '0', 'length': '100',
                'search[value]': '', 'search[regex]': 'false',
                'urun': product_id, 'model': '0', 'renk': '0',
                'order[0][column]': '0', 'order[0][dir]': 'desc'
            }

            logging.info(f"Test: Endpoint {endpoint} için request gönderiliyor...")
            logging.info(f"Test: Payload: {payload}")
            
            response = self._make_request("POST", endpoint, auth_type='cookie', data=payload, is_internal_call=True)
            
            logging.info(f"Test: Response status: {response.status_code}")
            logging.info(f"Test: Response content (ilk 200 char): {response.text[:200]}")
            
            response_json = response.json()
            logging.info(f"Test: JSON parse başarılı, data count: {len(response_json.get('data', []))}")

            ordered_urls = []
            for i, item in enumerate(response_json.get('data', [])):
                if len(item) > 2:
                    html_string = item[2]
                    logging.info(f"Test: Item {i} HTML: {html_string[:100]}...")
                    match = re.search(r'href="(https?://[^"]+/o_[^"]+)"', html_string)
                    if match:
                        url = match.group(1)
                        ordered_urls.append(url)
                        logging.info(f"Test: URL bulundu: {url}")

            result["success"] = True
            result["images_found"] = ordered_urls
            logging.info(f"Test: Toplam {len(ordered_urls)} görsel URL'si bulundu")
            
        except Exception as e:
            result["error"] = str(e)
            logging.error(f"Test: Hata oluştu: {e}")
        
        return result