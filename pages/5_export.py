# pages/5_export.py

import streamlit as st
import pandas as pd
import json
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
from shopify_sync import ShopifyAPI, SentosAPI
import re
import os # YENİ: Ortak ön-ek (prefix) bulmak için eklendi
import logging # YENİ: Hata ayıklama için eklendi

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# --- Sayfa Yapılandırması ve Yardımcı Fonksiyonlar ---
st.set_page_config(layout="wide", page_title="Liste Oluşturucu")

# Giriş kontrolü
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

def _get_apparel_sort_key(size_str):
    if not isinstance(size_str, str): return (3, 9999, size_str)
    size_upper = size_str.strip().upper()
    size_order_map = {'XXS': 0, 'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, 'XXL': 6, '2XL': 6, '3XL': 7, 'XXXL': 7, '4XL': 8, 'XXXXL': 8, '5XL': 9, 'XXXXXL': 9, 'TEK EBAT': 100, 'STANDART': 100}
    if size_upper in size_order_map: return (1, size_order_map[size_upper], size_str)
    numbers = re.findall(r'\d+', size_str)
    if numbers: return (2, int(numbers[0]), size_str)
    return (3, 9999, size_str)

@st.cache_data(ttl=600)
def get_collections(_shopify_api):
    return _shopify_api.get_all_collections()

def get_sentos_data_by_base_code(sentos_api, model_codes_to_fetch):
    """
    Verilen ANA ürün kodları listesini kullanarak Sentos'tan alış fiyatı ve doğrulanmış ana kod bilgisini çeker.
    """
    data_map = {} # Key: base_model_code, Value: {'purchase_price': ...}
    unique_model_codes = list(set(model_codes_to_fetch))
    total_codes = len(unique_model_codes)
    if total_codes == 0:
        return {}

    progress_bar = st.progress(0, "Sentos'tan veri çekiliyor...")
    
    for i, code in enumerate(unique_model_codes):
        if not code: continue
        try:
            sentos_product = sentos_api.get_product_by_sku(code)
            if sentos_product:
                price = sentos_product.get('purchase_price')
                # Gelen yanıttaki asıl ana SKU'yu doğrula
                verified_main_code = sentos_product.get('sku', code)
                data_map[code] = {
                    'verified_code': verified_main_code,
                    'purchase_price': float(str(price).replace(',', '.')) if price is not None else None
                }
        except Exception as e:
            # GÜNCELLENDİ: Hataları sessizce geçmek yerine loglayarak daha fazla bilgi sağlıyoruz.
            logging.warning(f"Sentos'tan '{code}' SKU'su için veri çekilirken bir hata oluştu: {e}")
            pass # get_product_by_sku içindeki loglama devam ediyor, bu ek bir güvence.
        progress_bar.progress((i + 1) / total_codes, f"Sentos'tan veri çekiliyor... ({i+1}/{total_codes})")
    
    progress_bar.empty()
    return data_map

# YENİ FONKSİYON: Varyant SKU listesinden en olası ana ürün kodunu bulur.
def get_base_code_from_skus(variant_skus):
    """
    Bir ürüne ait tüm varyant SKU'larının listesini alarak,
    en uzun ortak başlangıç kısmını (prefix) bulur ve bunu ana model kodu olarak döndürür.
    Bu, tek bir SKU'yu tireye göre bölmekten çok daha güvenilir bir yöntemdir.
    """
    # Boş veya geçersiz SKU'ları temizle
    skus = [s for s in variant_skus if s and isinstance(s, str)]
    if not skus:
        return ""

    # Eğer sadece bir SKU varsa, eski mantığı kullan (sondan tireyi at)
    if len(skus) == 1:
        last_hyphen_index = skus[0].rfind('-')
        if last_hyphen_index > 0:
            return skus[0][:last_hyphen_index]
        return skus[0]

    # Birden fazla SKU varsa, en uzun ortak başlangıcı bul
    common_prefix = os.path.commonprefix(skus)
    
    # Ortak kısmın sonunda tire varsa veya tam bir SKU ise olduğu gibi bırak,
    # Aksi halde en yakın tireye kadar geri kırp.
    if common_prefix and not common_prefix.endswith('-') and common_prefix not in skus:
        last_hyphen_index = common_prefix.rfind('-')
        if last_hyphen_index > 0:
            return common_prefix[:last_hyphen_index]
    
    return common_prefix.strip('-')


@st.cache_data(ttl=600)
def process_data(_shopify_api, _sentos_api, selected_collection_ids):
    status_text = st.empty()
    status_text.info("1/4: Shopify API'den tüm ürün verileri çekiliyor...")
    all_products = _shopify_api.get_all_products_for_export(progress_callback=status_text.text)

    if selected_collection_ids:
        filtered_products = [
            p for p in all_products 
            if p.get('collections') and not {c['node']['id'] for c in p['collections']['edges']}.isdisjoint(selected_collection_ids)
        ]
        products_data = filtered_products
    else:
        products_data = all_products
    
    status_text.info(f"2/4: {len(products_data)} ürün rapor için işleniyor...")
    processed_data, all_sizes, codes_with_no_price = {}, set(), set()

    for product in products_data:
        variants = product.get('variants', {}).get('edges', [])
        if not variants: continue
        
        variants_by_group = {}
        has_color_option = any('renk' in opt['name'].lower() for v in variants if v.get('node', {}).get('selectedOptions') for opt in v['node']['selectedOptions'])

        for v_edge in variants:
            v = v_edge['node']
            if not v or not v.get('selectedOptions'): continue
            group_key = 'N/A'
            if has_color_option:
                color_option = next((opt['value'] for opt in v['selectedOptions'] if opt['name'].lower() == 'renk'), None)
                if color_option is None: continue
                group_key = color_option
            if group_key not in variants_by_group: variants_by_group[group_key] = []
            variants_by_group[group_key].append(v)
        
        if not variants_by_group: continue
        
        # GÜNCELLENDİ: Ana model kodunu tahmin etme mantığı iyileştirildi.
        # Artık tek bir SKU yerine tüm varyant SKU'larını kullanarak daha akıllı bir tahmin yapıyoruz.
        all_variant_skus = [v['node']['sku'] for v in variants if v['node'] and v['node'].get('sku')]
        base_model_code_guess = get_base_code_from_skus(all_variant_skus)
        
        collection_names = ", ".join([c['node']['title'] for c in product.get('collections', {}).get('edges', [])])
        
        for group_key, group_variants in variants_by_group.items():
            key = (product['title'], group_key)
            image_data = product.get('featuredImage')
            image_url = image_data.get('url', '') if image_data else ''
            
            row = {"TÜR": collection_names, "GÖRSEL_URL": image_url, "MODEL KODU": base_model_code_guess,
                   "ÜRÜN LİNKİ": f"{_shopify_api.store_url}/products/{product['handle']}",
                   "RENK": group_key if has_color_option else '', "sizes": {}, "ALIŞ FİYATI": None}

            total_stock = 0
            for variant in group_variants:
                size_value = next((opt['value'] for opt in variant['selectedOptions'] if opt['name'].lower() == 'beden'), 'N/A')
                stock = variant.get('inventoryQuantity') or 0
                row["sizes"][size_value] = stock
                total_stock += stock
                all_sizes.add(size_value)
                if row["ALIŞ FİYATI"] is None:
                    unit_cost = variant.get('inventoryItem', {}).get('unitCost')
                    if unit_cost and unit_cost.get('amount') is not None:
                        row["ALIŞ FİYATI"] = float(unit_cost['amount'])

            row["TOPLAM STOK"] = total_stock
            if row["ALIŞ FİYATI"] is None and base_model_code_guess:
                codes_with_no_price.add(base_model_code_guess)
            processed_data[key] = row

    if codes_with_no_price:
        status_text.info(f"3/4: Shopify'da bulunamayan {len(codes_with_no_price)} ürün için Sentos'tan alış fiyatı çekiliyor...")
        sentos_data_map = get_sentos_data_by_base_code(_sentos_api, list(codes_with_no_price))
        for data in processed_data.values():
            base_code = data.get("MODEL KODU")
            if base_code in sentos_data_map:
                sentos_info = sentos_data_map[base_code]
                if data["ALIŞ FİYATI"] is None:
                    data["ALIŞ FİYATI"] = sentos_info.get('purchase_price')
                data["MODEL KODU"] = sentos_info.get('verified_code', base_code) # Sentos'tan gelen kodu ata

    status_text.info("4/4: Veriler son formata dönüştürülüyor...")
    sorted_sizes = sorted(list(all_sizes), key=_get_apparel_sort_key)
    final_rows = []
    for data in processed_data.values():
        new_row = {
            "TÜR": data["TÜR"],
            "GÖRSEL": f'=IMAGE("{data["GÖRSEL_URL"]}")' if data["GÖRSEL_URL"] else '',
            "MODEL KODU": data["MODEL KODU"], "ÜRÜN LİNKİ": data["ÜRÜN LİNKİ"], "RENK": data["RENK"]
        }
        for size in sorted_sizes: new_row[size] = data["sizes"].get(size, 0)
        new_row["TOPLAM STOK"] = data["TOPLAM STOK"]
        new_row["ALIŞ FİYATI"] = data["ALIŞ FİYATI"]
        final_rows.append(new_row)

    if not final_rows:
        status_text.warning("Seçilen kriterlere uygun veri bulunamadı.")
        return None
    
    df = pd.DataFrame(final_rows)
    status_text.empty()
    return df

def upload_to_gsheets(df, sheet_name):
    try:
        creds_json_str = st.session_state.get('gcp_service_account_json')
        creds_dict = json.loads(creds_json_str)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        try:
            spreadsheet = gc.open(sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            st.info(f"'{sheet_name}' adında bir e-tablo bulunamadı, yeni bir tane oluşturuluyor...")
            spreadsheet = gc.create(sheet_name)
            spreadsheet.share(creds_dict['client_email'], perm_type='user', role='writer')
        
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.clear()
        set_with_dataframe(worksheet, df, allow_formulas=True)
        return spreadsheet.url, worksheet
        
    except Exception as e:
        st.error(f"Google E-Tablolar'a bağlanırken hata oluştu: {e}")
        st.info("Ayarlar sayfasından Google anahtarınızı doğru girdiğinizden ve bu anahtarın e-posta adresini hedef E-Tablo ile paylaştığınızdan emin olun.")
        return None, None

# --- ARAYÜZ ---
st.markdown("<h1>📄 Koleksiyon Bazlı Google E-Tablolar Raporu</h1>", unsafe_allow_html=True)
st.markdown("<p>Shopify'daki ürünleri koleksiyonlara göre filtreleyerek stok ve fiyat bilgileriyle Google E-Tablolar'a aktarın.</p>", unsafe_allow_html=True)

if st.session_state.get('shopify_status') != 'connected' or not st.session_state.get('gcp_service_account_json'):
    st.warning("Bu özelliği kullanmak için lütfen 'Ayarlar' sayfasından hem Shopify hem de Google E-Tablolar bağlantı ayarlarını tamamlayın.")
    st.stop()

try:
    shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
    sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
    
    collections = get_collections(shopify_api)
    if not collections:
        st.info("Mağazanızda herhangi bir koleksiyon bulunamadı.")
        st.stop()

    collection_options = {c['title']: c['id'] for c in collections}
    
    st.subheader("1. Rapor Alınacak Koleksiyonları Seçin")
    selected_titles = st.multiselect("Koleksiyonlar (Boş bırakmak tüm ürünleri getirir)", options=collection_options.keys(), label_visibility="collapsed")
    selected_ids = [collection_options[title] for title in selected_titles]

    st.subheader("2. Google E-Tablo Adını Belirtin")
    g_sheet_name = st.text_input("Google E-Tablo Dosya Adı", "Vervegrand Stok Raporu", label_visibility="collapsed")

    if st.button("🚀 Raporu Google E-Tablolar'a Gönder", type="primary", use_container_width=True):
        if not g_sheet_name:
            st.warning("Lütfen bir Google E-Tablo dosya adı girin.")
        else:
            df = process_data(shopify_api, sentos_api, set(selected_ids))
            if df is not None:
                with st.spinner(f"Veriler '{g_sheet_name}' adlı e-tabloya yükleniyor..."):
                    sheet_url, worksheet = upload_to_gsheets(df, g_sheet_name)
                if sheet_url:
                    st.success(f"✅ Rapor başarıyla '{g_sheet_name}' e-tablosuna aktarıldı!")
                    st.markdown(f"**[E-Tabloyu Görüntüle]({sheet_url})**")

except Exception as e:
    st.error(f"Rapor oluşturulurken bir hata oluştu: {e}")
    st.exception(e)