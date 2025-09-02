"""
API Yapı Analizi - Shopify ve Sentos API'larının gerçek yapılarını incele
"""

import requests
import json
from requests.auth import HTTPBasicAuth
import config_manager

def analyze_shopify_product():
    """Mevcut bir Shopify ürününün tam yapısını analiz et"""
    
    credentials = config_manager.load_all_keys()
    
    if not credentials:
        print("❌ Ayarlar bulunamadı!")
        return None
    
    headers = {
        'X-Shopify-Access-Token': credentials['shopify_token'],
        'Content-Type': 'application/json'
    }
    
    # İlk ürünü al
    url = f"https://{credentials['shopify_store']}/admin/api/2023-10/products.json?limit=1"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('products'):
                product = data['products'][0]
                print("🔍 SHOPIFY ÜRÜN YAPISI:")
                print("=" * 80)
                print(json.dumps(product, indent=2, ensure_ascii=False))
                print("=" * 80)
                
                # Ana alanları listele
                print("\n📋 SHOPIFY ANA ALANLAR:")
                for key in product.keys():
                    value_type = type(product[key]).__name__
                    if isinstance(product[key], list) and product[key]:
                        item_type = type(product[key][0]).__name__
                        print(f"  {key}: {value_type}[{item_type}] (count: {len(product[key])})")
                    else:
                        print(f"  {key}: {value_type}")
                
                # Variants yapısını detaylandır
                if product.get('variants'):
                    variant = product['variants'][0]
                    print("\n🎯 SHOPIFY VARIANT YAPISI:")
                    for key in variant.keys():
                        value_type = type(variant[key]).__name__
                        print(f"  {key}: {value_type}")
                
                return product
            else:
                print("❌ Shopify'da ürün bulunamadı!")
                return None
        else:
            print(f"❌ Shopify API hatası: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Shopify analiz hatası: {str(e)}")
        return None

def analyze_sentos_product():
    """Sentos API'dan bir ürünün tam yapısını analiz et"""
    
    credentials = config_manager.load_all_keys()
    
    if not credentials:
        print("❌ Ayarlar bulunamadı!")
        return None
    
    auth = HTTPBasicAuth(credentials['sentos_api_key'], credentials['sentos_api_secret'])
    
    # İlk ürünü al
    url = f"{credentials['sentos_api_url']}/product?page=0&size=1"
    
    try:
        response = requests.get(url, auth=auth)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                product = data['data'][0]
                print("🔍 SENTOS ÜRÜN YAPISI:")
                print("=" * 80)
                print(json.dumps(product, indent=2, ensure_ascii=False))
                print("=" * 80)
                
                # Ana alanları listele
                print("\n📋 SENTOS ANA ALANLAR:")
                for key in product.keys():
                    value_type = type(product[key]).__name__
                    if isinstance(product[key], list) and product[key]:
                        item_type = type(product[key][0]).__name__
                        print(f"  {key}: {value_type}[{item_type}] (count: {len(product[key])})")
                    else:
                        print(f"  {key}: {value_type}")
                
                # Variants yapısını detaylandır
                if product.get('variants'):
                    variant = product['variants'][0]
                    print("\n🎯 SENTOS VARIANT YAPISI:")
                    for key in variant.keys():
                        value_type = type(variant[key]).__name__
                        if isinstance(variant[key], list) and variant[key]:
                            item_type = type(variant[key][0]).__name__
                            print(f"  {key}: {value_type}[{item_type}] (count: {len(variant[key])})")
                        else:
                            print(f"  {key}: {value_type}")
                
                return product
            else:
                print("❌ Sentos'ta ürün bulunamadı!")
                return None
        else:
            print(f"❌ Sentos API hatası: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Sentos analiz hatası: {str(e)}")
        return None

def compare_structures(shopify_product, sentos_product):
    """İki API yapısını karşılaştır ve mapping öner"""
    
    if not shopify_product or not sentos_product:
        print("❌ Karşılaştırma için her iki ürün de gerekli!")
        return
    
    print("\n🔄 ALAN KARŞILAŞTIRMASI:")
    print("=" * 80)
    
    # Temel mapping önerileri
    mapping_suggestions = {
        # Shopify Field -> Sentos Field
        'title': ['name', 'title', 'product_name'],
        'body_html': ['description', 'description_detail', 'product_description'],
        'vendor': ['brand', 'manufacturer', 'supplier'],
        'product_type': ['category', 'type', 'product_type'],
        'tags': ['tags', 'categories', 'keywords'],
        'handle': ['slug', 'permalink', 'url_key'],
        'variants': ['variants', 'options', 'variations']
    }
    
    print("📋 ÖNERİLEN ALAN EŞLEŞTİRMELERİ:")
    for shopify_field, sentos_candidates in mapping_suggestions.items():
        print(f"\nShopify.{shopify_field} -> Sentos:")
        found_fields = []
        for candidate in sentos_candidates:
            if candidate in sentos_product:
                found_fields.append(f"✅ {candidate}")
            else:
                found_fields.append(f"❌ {candidate}")
        print("  " + ", ".join(found_fields))
    
    # Variant karşılaştırması
    if shopify_product.get('variants') and sentos_product.get('variants'):
        shopify_variant = shopify_product['variants'][0]
        sentos_variant = sentos_product['variants'][0]
        
        print(f"\n🎯 VARIANT ALAN KARŞILAŞTIRMASI:")
        variant_mapping = {
            'price': ['price', 'sale_price', 'cost'],
            'sku': ['sku', 'code', 'product_code'],
            'barcode': ['barcode', 'upc', 'ean'],
            'inventory_quantity': ['stock', 'quantity', 'inventory'],
            'option1': ['color', 'size', 'option1'],
            'option2': ['size', 'color', 'option2']
        }
        
        for shopify_field, sentos_candidates in variant_mapping.items():
            print(f"\nVariant.{shopify_field} -> Sentos:")
            found_fields = []
            for candidate in sentos_candidates:
                if candidate in sentos_variant:
                    found_fields.append(f"✅ {candidate}")
                else:
                    found_fields.append(f"❌ {candidate}")
            print("  " + ", ".join(found_fields))

def create_minimal_shopify_product():
    """En minimal Shopify ürün oluşturma denemesi"""
    
    credentials = config_manager.load_all_keys()
    
    if not credentials:
        print("❌ Ayarlar bulunamadı!")
        return None
    
    headers = {
        'X-Shopify-Access-Token': credentials['shopify_token'],
        'Content-Type': 'application/json'
    }
    
    url = f"https://{credentials['shopify_store']}/admin/api/2023-10/products.json"
    
    # Farklı minimal kombinasyonları test et
    test_cases = [
        {
            'name': 'Sadece title',
            'payload': {
                'product': {
                    'title': 'Test Product - Only Title'
                }
            }
        },
        {
            'name': 'Title + vendor',
            'payload': {
                'product': {
                    'title': 'Test Product - Title + Vendor',
                    'vendor': 'Test Vendor'
                }
            }
        },
        {
            'name': 'Title + product_type',
            'payload': {
                'product': {
                    'title': 'Test Product - Title + Type',
                    'product_type': 'Test Type'
                }
            }
        },
        {
            'name': 'Title + vendor + product_type',
            'payload': {
                'product': {
                    'title': 'Test Product - Complete',
                    'vendor': 'Test Vendor',
                    'product_type': 'Test Type'
                }
            }
        },
        {
            'name': 'Title + status',
            'payload': {
                'product': {
                    'title': 'Test Product - With Status',
                    'status': 'draft'
                }
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 TEST: {test_case['name']}")
        print(f"📦 Payload: {json.dumps(test_case['payload'], indent=2)}")
        
        try:
            response = requests.post(url, headers=headers, json=test_case['payload'])
            
            if response.status_code == 201:
                created_product = response.json().get('product', {})
                print(f"✅ BAŞARILI! Product ID: {created_product.get('id')}")
                
                # Oluşan ürünü sil (test için)
                delete_url = f"https://{credentials['shopify_store']}/admin/api/2023-10/products/{created_product['id']}.json"
                delete_response = requests.delete(delete_url, headers=headers)
                if delete_response.status_code == 200:
                    print("🗑️ Test ürünü silindi")
                
                return test_case['payload']['product']
            else:
                print(f"❌ BAŞARISIZ: {response.status_code}")
                print(f"📋 Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Hata: {str(e)}")
    
    return None

if __name__ == "__main__":
    print("🚀 API YAPI ANALİZİ BAŞLATIYOR...")
    print("=" * 80)
    
    # 1. Shopify ürün yapısını analiz et
    shopify_product = analyze_shopify_product()
    
    print("\n" + "=" * 80)
    
    # 2. Sentos ürün yapısını analiz et
    sentos_product = analyze_sentos_product()
    
    print("\n" + "=" * 80)
    
    # 3. Yapıları karşılaştır
    compare_structures(shopify_product, sentos_product)
    
    print("\n" + "=" * 80)
    
    # 4. Minimal Shopify ürün oluşturma testi
    print("\n🧪 MİNİMAL SHOPIFY ÜRÜN OLUŞTURMA TESTİ:")
    minimal_product = create_minimal_shopify_product()
    
    if minimal_product:
        print(f"\n✅ EN MİNİMAL BAŞARILI SHOPIFY ÜRÜN YAPISI:")
        print(json.dumps(minimal_product, indent=2, ensure_ascii=False))
    else:
        print("\n❌ Hiçbir minimal kombinasyon başarılı olmadı!")
    
    print("\n🏁 ANALİZ TAMAMLANDI!")
