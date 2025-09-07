# pages/6_Fiyat_Hesaplayıcı.py (Akıllı Varyant Eşleştirme ve Ana Ürün Arayüzü)

import streamlit as st
import pandas as pd
import math
import numpy as np
import json
from io import StringIO

# Proje dizinindeki modülleri import et
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shopify_sync import ShopifyAPI, SentosAPI
import gsheets_manager

# --- Sayfa Kurulumu ve Kontroller ---
def load_css():
    """Mevcut style.css dosyasını yükler."""
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

load_css()


# --- YARDIMCI FONKSİYONLAR ---
def get_base_code_from_sku(sku):
    """Varyant SKU'sundan ana ürün kodunu tahmin eder."""
    if not sku or not isinstance(sku, str):
        return None
    return sku.split('-', 1)[0]

def get_base_name(product_name):
    """Ürün adından varyant bilgilerini ('- Renk / Beden') temizler."""
    if not product_name or not isinstance(product_name, str):
        return "İsimsiz Ürün"
    return product_name.split(' - ')[0].strip()

def process_sentos_data(product_list):
    """
    Sentos'tan gelen veriyi işleyerek iki ayrı DataFrame oluşturur:
    1. df_variants: Tüm varyantları içeren detaylı liste.
    2. df_main_products: Arayüzde gösterilecek, sadeleştirilmiş ana ürün listesi.
    """
    all_variants_rows = []
    
    for p in product_list:
        main_price_str = str(p.get('purchase_price') or p.get('AlisFiyati') or '0').replace(',', '.')
        main_purchase_price = float(main_price_str) if main_price_str else 0.0

        variants = p.get('variants', [])
        
        if not variants:
            base_sku = p.get('sku')
            all_variants_rows.append({
                'base_sku': base_sku,
                'MODEL KODU': base_sku,
                'ÜRÜN ADI': p.get('name'),
                'ALIŞ FİYATI': main_purchase_price
            })
        else:
            for v in variants:
                variant_price_str = str(v.get('purchase_price') or v.get('AlisFiyati') or '0').replace(',', '.')
                variant_purchase_price = float(variant_price_str) if variant_price_str else 0.0
                final_price = variant_purchase_price if variant_purchase_price > 0 else main_purchase_price
                
                base_sku = get_base_code_from_sku(v.get('sku')) or p.get('sku')
                
                color = v.get('color', '').strip()
                model_data = v.get('model', '')
                size = (model_data.get('value', '') if isinstance(model_data, dict) else str(model_data)).strip()
                attributes = [attr for attr in [color, size] if attr]
                suffix = " - " + " / ".join(attributes) if attributes else ""
                variant_name = f"{p.get('name', '')}{suffix}".strip()

                all_variants_rows.append({
                    'base_sku': base_sku,
                    'MODEL KODU': v.get('sku'),
                    'ÜRÜN ADI': variant_name,
                    'ALIŞ FİYATI': final_price
                })
    
    if not all_variants_rows:
        return pd.DataFrame(), pd.DataFrame()

    df_variants = pd.DataFrame(all_variants_rows)
    
    # Ana ürün listesini oluştur: base_sku'ya göre grupla ve ilk satırı al
    df_main_products = df_variants.drop_duplicates(subset=['base_sku'], keep='first').copy()
    
    # Ana ürün listesindeki isimleri ve model kodlarını temizle
    df_main_products['ÜRÜN ADI'] = df_main_products.apply(lambda row: get_base_name(row['ÜRÜN ADI']), axis=1)
    df_main_products['MODEL KODU'] = df_main_products['base_sku']
    
    return df_variants, df_main_products[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI']]


def apply_rounding(price, method):
    if method == "Yukarı Yuvarla":
        if price % 10 != 9.99 and price % 10 != 9: return math.floor(price / 10) * 10 + 9.99
        elif price % 1 == 0: return price - 0.01
        return price
    elif method == "Aşağı Yuvarla":
        return math.floor(price / 10) * 10 - 0.01 if price > 10 else 9.99
    return price

# --- Session State Başlatma ---
st.session_state.setdefault('calculated_df', None)
st.session_state.setdefault('df_for_display', None)
st.session_state.setdefault('df_variants', None)

# --- ARAYÜZ ---
st.markdown("""
<div class="main-header">
    <h1>📊 Fiyat Stratejisi Panosu</h1>
    <p>Fiyat senaryoları oluşturun, Google E-Tablolar'a kaydedin ve Shopify'a gönderin.</p>
</div>
""", unsafe_allow_html=True)

# Adım 1: Veri Yükleme
st.subheader("Adım 1: Ürün Verilerini Yükle")
if st.session_state.df_for_display is None:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Sentos'tan Yeni Fiyat Listesi Çek", use_container_width=True):
            with st.spinner("Sentos API'den veriler çekiliyor ve işleniyor..."):
                try:
                    sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
                    all_products = sentos_api.get_all_products()
                    if not all_products:
                        st.error("❌ Sentos API'den hiç ürün verisi gelmedi.")
                    else:
                        st.session_state.df_variants, st.session_state.df_for_display = process_sentos_data(all_products)
                        st.toast(f"{len(st.session_state.df_for_display)} ana ürün ve {len(st.session_state.df_variants)} varyant bulundu.")
                        st.rerun()
                except Exception as e: 
                    st.error(f"API hatası: {e}")
    # ... (Google Sheets yükleme butonu aynı kalabilir) ...
else:
    count = len(st.session_state.df_for_display)
    st.success(f"✅ {count} ana ürün verisi hafızada yüklü.")
    if st.button("🧹 Verileri Temizle ve Baştan Başla", use_container_width=True):
        st.session_state.calculated_df = None
        st.session_state.df_for_display = None
        st.session_state.df_variants = None
        st.rerun()

if st.session_state.df_for_display is not None:
    st.markdown("---"); st.subheader("Adım 2: Fiyatlandırma Kurallarını Uygula")
    with st.container(border=True):
        # ... (Fiyatlandırma kuralı arayüzü aynı kalır) ...
        c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
        markup_type = c1.radio("Kâr Marjı Tipi", ["Yüzde Ekle (%)", "Çarpan Kullan (x)"], key="markup_type")
        markup_value = c1.number_input("Değer", min_value=0.0, value=100.0 if markup_type == "Yüzde Ekle (%)" else 2.5, step=0.1, key="markup_value")
        add_vat = c2.checkbox("Satışa KDV Dahil Et", value=True, key="add_vat")
        vat_rate = c2.number_input("KDV Oranı (%)", 0, 100, 10, disabled=not add_vat, key="vat_rate")
        rounding_method_text = c3.radio("Fiyat Yuvarlama", ["Yok", "Yukarı (X9.99)", "Aşağı (X9.99)"], index=1, key="rounding")
        
        if c4.button("💰 Fiyatları Hesapla", type="primary", use_container_width=True):
            df = st.session_state.df_for_display.copy()
            df['SATIS_FIYATI_KDVSIZ'] = df['ALIŞ FİYATI'] * (1 + markup_value / 100) if markup_type == "Yüzde Ekle (%)" else df['ALIŞ FİYATI'] * markup_value
            df['SATIS_FIYATI_KDVLI'] = df['SATIS_FIYATI_KDVSIZ'] * (1 + vat_rate / 100) if add_vat else df['SATIS_FIYATI_KDVSIZ']
            rounding_method_arg = rounding_method_text.replace(" (X9.99)", "").replace("Aşağı", "Aşağı Yuvarla").replace("Yukarı", "Yukarı Yuvarla")
            df['NIHAI_SATIS_FIYATI'] = df['SATIS_FIYATI_KDVLI'].apply(lambda p: apply_rounding(p, rounding_method_arg))
            revenue = df['NIHAI_SATIS_FIYATI'] / (1 + vat_rate / 100) if add_vat else df['NIHAI_SATIS_FIYATI']
            df['KÂR'] = revenue - df['ALIŞ FİYATI']
            df['KÂR ORANI (%)'] = np.divide(df['KÂR'], df['ALIŞ FİYATI'], out=np.zeros_like(df['KÂR']), where=df['ALIŞ FİYATI']!=0) * 100
            st.session_state.calculated_df = df
            st.rerun()

if st.session_state.calculated_df is not None:
    st.markdown("---"); st.subheader("Adım 3: Senaryoları Analiz Et")
    df = st.session_state.calculated_df
    # ... (Tüm analiz tabloları aynı kalır, çünkü 'calculated_df' ana ürün bazındadır) ...
    with st.expander("Tablo 1: Ana Fiyat ve Kârlılık Listesi (Referans)", expanded=True):
        main_df_display = df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', 'SATIS_FIYATI_KDVSIZ', 'NIHAI_SATIS_FIYATI', 'KÂR', 'KÂR ORANI (%)']]
        st.dataframe(main_df_display.style.format({
            'ALIŞ FİYATI': '{:,.2f} ₺', 'SATIS_FIYATI_KDVSIZ': '{:,.2f} ₺', 'NIHAI_SATIS_FIYATI': '{:,.2f} ₺',
            'KÂR': '{:,.2f} ₺', 'KÂR ORANI (%)': '{:.2f}%'
        }), use_container_width=True)
    # Diğer analiz expander'ları da buraya eklenebilir.

    st.markdown("---"); st.subheader("Adım 4: Kaydet ve Shopify'a Gönder")
    # ... (Google Sheets kaydetme butonu aynı kalabilir) ...
    update_choice = st.selectbox("Hangi Fiyat Listesini Göndermek İstersiniz?", ["Ana Fiyatlar", "İndirimli Fiyatlar"])
    if st.button(f"🚀 {update_choice} Shopify'a Gönder", use_container_width=True, type="primary"):
        with st.spinner("Varyant fiyatları hazırlanıyor ve Shopify ile eşleştiriliyor..."):
            # 1. Ana ürünler için hesaplanan fiyatları al
            calculated_prices = st.session_state.calculated_df[['MODEL KODU', 'NIHAI_SATIS_FIYATI']].rename(columns={'MODEL KODU': 'base_sku'})
            
            # 2. Arka plandaki detaylı varyant listesiyle bu fiyatları birleştir
            df_to_send = pd.merge(st.session_state.df_variants, calculated_prices, on='base_sku', how='left')

            # 3. Shopify'a göndermek için varyant SKU listesini oluştur
            skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
            shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)
            
            updates = []
            for _, row in df_to_send.iterrows():
                sku = str(row['MODEL KODU'])
                if sku in variant_map:
                    update_payload = {
                        "variant_id": variant_map[sku],
                        "price": f"{row['NIHAI_SATIS_FIYATI']:.2f}",
                        "compare_at_price": None # İstenirse bu kısım da eklenebilir
                    }
                    updates.append(update_payload)

        if updates:
            st.info(f"{len(updates)} varyantın fiyatı Shopify'a güncelleniyor...")
            with st.spinner("Fiyatlar güncelleniyor..."):
                results = shopify_api.bulk_update_variant_prices(updates)
            st.success(f"İşlem Tamamlandı! ✅ {results.get('success', 0)} varyant başarıyla güncellendi.")
            if results.get('failed', 0) > 0:
                st.error(f"❌ {results.get('failed', 0)} varyant güncellenirken hata oluştu.")
                with st.expander("Hata Detayları"): st.json(results.get('errors', []))
        else:
            st.warning("Shopify'da eşleşen ve güncellenecek varyant bulunamadı.")