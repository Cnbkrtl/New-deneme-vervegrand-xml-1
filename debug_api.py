#!/usr/bin/env python3
"""
Debug script to inspect Shopify and Sentos API structures
"""

import json
import requests
from requests.auth import HTTPBasicAuth
import sys

def get_shopify_product_structure():
    """Get Shopify product structure"""
    try:
        # Config'den bilgileri al
        from config_manager import ConfigManager
        config = ConfigManager()
        
        store_url = config.get('shopify_store_url')
        access_token = config.get('shopify_access_token')
        
        if not store_url or not access_token:
            print("❌ Shopify credentials not found in config")
            return None
        
        # İlk ürünü çek
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
        
        url = f"{store_url}/admin/api/2023-10/products.json?limit=1"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('products'):
                product = data['products'][0]
                print("🏪 SHOPIFY PRODUCT STRUCTURE:")
                print("="*50)
                print(json.dumps(product, indent=2))
                print("="*50)
                return product
        else:
            print(f"❌ Shopify API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting Shopify product: {e}")
        return None

def get_sentos_product_structure():
    """Get Sentos product structure"""
    try:
        # Config'den bilgileri al
        from config_manager import ConfigManager
        config = ConfigManager()
        
        api_url = config.get('sentos_api_url')
        api_key = config.get('sentos_api_key') 
        api_secret = config.get('sentos_api_secret')
        
        if not all([api_url, api_key, api_secret]):
            print("❌ Sentos credentials not found in config")
            return None
        
        # İlk ürünü çek
        url = f"{api_url.strip('/')}/products?page=1&per_page=1"
        response = requests.get(
            url,
            auth=HTTPBasicAuth(api_key, api_secret),
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and len(data['data']) > 0:
                product = data['data'][0]
                print("📄 SENTOS PRODUCT STRUCTURE:")
                print("="*50)
                print(json.dumps(product, indent=2))
                print("="*50)
                return product
        else:
            print(f"❌ Sentos API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting Sentos product: {e}")
        return None

def compare_structures(shopify_product, sentos_product):
    """Compare the two structures and suggest mappings"""
    if not shopify_product or not sentos_product:
        print("❌ Cannot compare - missing product data")
        return
    
    print("\n🔍 FIELD COMPARISON:")
    print("="*50)
    
    # Shopify key fields
    shopify_fields = {
        'id': shopify_product.get('id'),
        'title': shopify_product.get('title'),
        'body_html': shopify_product.get('body_html'),
        'vendor': shopify_product.get('vendor'),
        'product_type': shopify_product.get('product_type'),
        'tags': shopify_product.get('tags'),
        'status': shopify_product.get('status'),
        'variants_count': len(shopify_product.get('variants', [])),
        'options_count': len(shopify_product.get('options', [])),
    }
    
    # Sentos key fields  
    sentos_fields = {
        'id': sentos_product.get('id'),
        'name': sentos_product.get('name'),
        'description': sentos_product.get('description'),
        'brand': sentos_product.get('brand'),
        'sku': sentos_product.get('sku'),
        'price': sentos_product.get('price'),
        'sale_price': sentos_product.get('sale_price'),
        'variants_count': len(sentos_product.get('variants', [])),
        'stocks_count': len(sentos_product.get('stocks', [])),
    }
    
    print("SHOPIFY FIELDS:")
    for key, value in shopify_fields.items():
        print(f"  {key}: {value}")
    
    print("\nSENTOS FIELDS:")
    for key, value in sentos_fields.items():
        print(f"  {key}: {value}")
    
    print("\n📋 SUGGESTED MAPPINGS:")
    print("="*30)
    print("Sentos → Shopify")
    print("name → title")
    print("description → body_html") 
    print("brand → vendor")
    print("brand → product_type")
    print("sku → variants[0].sku")
    print("sale_price/price → variants[0].price")
    
    # Check if we have variants
    if shopify_product.get('variants'):
        print(f"\n🔍 SHOPIFY VARIANT STRUCTURE (first variant):")
        variant = shopify_product['variants'][0]
        print(json.dumps(variant, indent=2))
    
    if sentos_product.get('variants'):
        print(f"\n🔍 SENTOS VARIANT STRUCTURE (first variant):")
        variant = sentos_product['variants'][0]
        print(json.dumps(variant, indent=2))

if __name__ == "__main__":
    print("🔍 Analyzing API Structures...")
    
    shopify_product = get_shopify_product_structure()
    print("\n" + "="*50)
    
    sentos_product = get_sentos_product_structure()
    print("\n" + "="*50)
    
    compare_structures(shopify_product, sentos_product)
