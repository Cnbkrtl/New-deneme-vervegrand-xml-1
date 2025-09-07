# pages/6_Fiyat_Hesaplayıcı.py (Doğru Ana Ürün Gruplama Mantığı)

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
import data_manager

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
# <<< DÜZELTME BAŞLANGICI: Fonksiyon, SKU tahmin etmek yerine doğrudan ana ürün verisini kullanıyor >>>
def process_sentos_data(product_list):
    """
    Sentos'tan gelen ürün listesini işler. Ana ürünleri doğrudan sayar ve
    varyantları bu ana ürünlerle ilişkilendirir. Bu, en doğru gruplama yöntemidir.
    """
    all_variants_rows = []
    main_products_rows = []

    for p in product_list:
        # Ana ürün bilgilerini al
        main_sku = p.get('sku')
        main_name = p.get('name')
        try:
            main_price_str = str(p.get('purchase_price') or p.get('AlisFiyati') or '0').replace(',', '.')
            main_purchase_price = float(main_price_str)
        except (ValueError, TypeError):
            main_purchase_price = 0.0

        # Ana ürünü, gösterge listesi için ekle
        main_products_rows.append({
            'MODEL KODU': main_sku,
            'ÜRÜN ADI': main_name,
            'ALIŞ FİYATI': main_purchase_price
        })

        variants = p.get('variants', [])
        
        # Eğer ürünün varyantı yoksa, kendisini teknik listeye de ekle
        if not variants:
            all_variants_rows.append({
                'base_sku': main_sku,
                'MODEL KODU': main_sku,
                'ÜRÜN ADI': main_name,
                'ALIŞ FİYATI': main_purchase_price
            })
        # Eğer varyantları varsa, her bir varyantı ana SKU ile ilişkilendirerek ekle
        else:
            for v in variants:
                try:
                    variant_price_str = str(v.get('purchase_price') or v.get('AlisFiyati') or '0').replace(',', '.')
                    variant_purchase_price = float(variant_price_str)
                except (ValueError, TypeError):
                    variant_purchase_price = 0.0
                
                final_price = variant_purchase_price if variant_purchase_price > 0 else main_purchase_price
                
                color = v.get('color', '').strip()
                model_data = v.get('model', '')
                size = (model_data.get('value', '') if isinstance(model_data, dict) else str(model_data)).strip()
                attributes = [attr for attr in [color, size] if attr]
                suffix = " - " + " / ".join(attributes) if attributes else ""
                variant_name = f"{main_name}{suffix}".strip()

                all_variants_rows.append({
                    'base_sku': main_sku,  # Ana ürün SKU'su ile ilişkilendir
                    'MODEL KODU': v.get('sku'),
                    'ÜRÜN ADI': variant_name,
                    'ALIŞ FİYATI': final_price
                })
    
    df_variants = pd.DataFrame(all_variants_rows)
    df_main_products = pd.DataFrame(main_products_rows)
    
    return df_variants, df_main_products
# <<< DÜZELTME SONU >>>


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
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 Sentos'tan Yeni Fiyat Listesi Çek", use_container_width=True):
            progress_bar = st.progress(0, text="Sentos API'ye bağlanılıyor...")
            
            def progress_callback(update):
                progress = update.get('progress', 0)
                message = update.get('message', 'Veriler işleniyor...')
                progress_bar.progress(progress / 100.0, text=message)
            
            try:
                sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
                all_products = sentos_api.get_all_products(progress_callback=progress_callback)
                
                progress_bar.progress(100, text="Veriler işleniyor ve gruplanıyor...")
                if not all_products:
                    st.error("❌ Sentos API'den hiç ürün verisi gelmedi.")
                    progress_bar.empty()
                else:
                    df_variants, df_main = process_sentos_data(all_products)
                    st.session_state.df_variants = df_variants
                    st.session_state.df_for_display = df_main
                    username = st.session_state["username"]
                    data_manager.save_user_data(username, 
                                                df_variants_json=df_variants.to_json(orient='split'),
                                                df_for_display_json=df_main.to_json(orient='split'))
                    progress_bar.empty()
                    st.toast("Veriler çekildi ve yerel olarak kaydedildi.")
                    st.rerun()
            except Exception as e: 
                if 'progress_bar' in locals():
                    progress_bar.empty()
                st.error(f"API hatası: {e}")

    with col2:
        if st.button("📂 Kayıtlı Veriyi Yerelden Yükle", use_container_width=True):
            with st.spinner("Yerel veriler yükleniyor..."):
                username = st.session_state["username"]
                user_data = data_manager.load_user_data(username)
                if user_data:
                    st.session_state.df_variants = pd.read_json(StringIO(user_data['df_variants_json']), orient='split')
                    st.session_state.df_for_display = pd.read_json(StringIO(user_data['df_for_display_json']), orient='split')
                    if user_data.get('calculated_df_json'):
                        st.session_state.calculated_df = pd.read_json(StringIO(user_data['calculated_df_json']), orient='split')
                    st.toast("Kayıtlı veriler yerelden yüklendi.")
                    st.rerun()
                else:
                    st.warning("Daha önce kaydedilmiş yerel veri bulunamadı.")
    
    with col3:
        if st.button("📄 Kayıtlı Veriyi G-Sheets'ten Yükle", use_container_width=True):
            with st.spinner("Google E-Tablolardan veriler yükleniyor..."):
                loaded_df = gsheets_manager.load_pricing_data_from_gsheets()
            if loaded_df is not None and not loaded_df.empty:
                st.session_state.calculated_df = loaded_df
                st.session_state.df_for_display = loaded_df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI']]
                st.toast("Veriler Google E-Tablolar'dan yüklendi.")
                st.rerun()
            else:
                st.warning("Google E-Tablolar'dan veri yüklenemedi veya dosya boş.")

else:
    count = len(st.session_state.df_for_display)
    st.success(f"✅ {count} ana ürün verisi hafızada yüklü.")
    if st.button("🧹 Verileri Temizle ve Baştan Başla", use_container_width=True):
        st.session_state.calculated_df = None
        st.session_state.df_for_display = None
        st.session_state.df_variants = None
        data_manager.delete_user_data(st.session_state["username"])
        st.rerun()

if st.session_state.df_for_display is not None:
    st.markdown("---"); st.subheader("Adım 2: Fiyatlandırma Kurallarını Uygula")
    with st.container(border=True):
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
            
            username = st.session_state["username"]
            data_manager.save_user_data(username, 
                                        df_variants_json=st.session_state.df_variants.to_json(orient='split'),
                                        df_for_display_json=st.session_state.df_for_display.to_json(orient='split'),
                                        calculated_df_json=df.to_json(orient='split'))
            st.toast("Fiyatlar hesaplandı ve yerel olarak kaydedildi.")
            st.rerun()

if st.session_state.calculated_df is not None:
    st.markdown("---"); st.subheader("Adım 3: Senaryoları Analiz Et")
    df = st.session_state.calculated_df
    
    with st.expander("Tablo 1: Ana Fiyat ve Kârlılık Listesi (Referans)", expanded=True):
        main_df_display = df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', 'SATIS_FIYATI_KDVSIZ', 'NIHAI_SATIS_FIYATI', 'KÂR', 'KÂR ORANI (%)']]
        st.dataframe(main_df_display.style.format({
            'ALIŞ FİYATI': '{:,.2f} ₺', 'SATIS_FIYATI_KDVSIZ': '{:,.2f} ₺', 'NIHAI_SATIS_FIYATI': '{:,.2f} ₺',
            'KÂR': '{:,.2f} ₺', 'KÂR ORANI (%)': '{:.2f}%'
        }), use_container_width=True)
    
    with st.expander("Tablo 2: Perakende İndirim Analizi", expanded=True):
        retail_discount = st.slider("İndirim Oranı (%)", 0, 50, 10, 5, key="retail_slider")
        retail_df = df.copy()
        retail_df['İNDİRİM ORANI (%)'] = retail_discount
        retail_df['İNDİRİMLİ SATIŞ FİYATI'] = retail_df['NIHAI_SATIS_FIYATI'] * (1 - retail_discount / 100)
        revenue_after_discount = retail_df['İNDİRİMLİ SATIŞ FİYATI'] / (1 + vat_rate / 100)
        retail_df['İNDİRİM SONRASI KÂR'] = revenue_after_discount - retail_df['ALIŞ FİYATI']
        retail_df['İNDİRİM SONRASI KÂR ORANI (%)'] = np.divide(retail_df['İNDİRİM SONRASI KÂR'], retail_df['ALIŞ FİYATI'], out=np.zeros_like(retail_df['İNDİRİM SONRASI KÂR']), where=retail_df['ALIŞ FİYATI']!=0) * 100
        discount_df_display = retail_df[['MODEL KODU', 'ÜRÜN ADI', 'NIHAI_SATIS_FIYATI', 'İNDİRİM ORANI (%)', 'İNDİRİMLİ SATIŞ FİYATI', 'İNDİRİM SONRASI KÂR', 'İNDİRİM SONRASI KÂR ORANI (%)']]
        st.dataframe(discount_df_display.style.format({
            'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', 'İNDİRİM ORANI (%)': '{:.0f}%', 'İNDİRİMLİ SATIŞ FİYATI': '{:,.2f} ₺',
            'İNDİRİM SONRASI KÂR': '{:,.2f} ₺', 'İNDİRİM SONRASI KÂR ORANI (%)': '{:.2f}%'
        }), use_container_width=True)

    with st.expander("Tablo 3: Toptan Satış Fiyat Analizi", expanded=True):
        wholesale_method = st.radio("Toptan Fiyat Yöntemi", ('Çarpanla', 'İndirimle'), horizontal=True, key="ws_method")
        wholesale_df = df.copy()
        if wholesale_method == 'Çarpanla':
            ws_multiplier = st.number_input("Toptan Çarpanı", 1.0, 5.0, 1.8, 0.1)
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = wholesale_df["ALIŞ FİYATI"] * ws_multiplier
        else:
            ws_discount = st.slider("Perakende Fiyatından İndirim (%)", 10, 70, 40, 5, key="ws_discount")
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = (wholesale_df["NIHAI_SATIS_FIYATI"] / (1 + vat_rate / 100)) * (1 - ws_discount / 100)
        wholesale_df["TOPTAN FİYAT (KDV'li)"] = wholesale_df["TOPTAN FİYAT (KDV'siz)"] * (1 + vat_rate / 100)
        wholesale_df['TOPTAN KÂR'] = wholesale_df["TOPTAN FİYAT (KDV'siz)"] - wholesale_df["ALIŞ FİYATI"]
        wholesale_df_display = wholesale_df[['MODEL KODU', 'ÜRÜN ADI', 'NIHAI_SATIS_FIYATI', "TOPTAN FİYAT (KDV'siz)", "TOPTAN FİYAT (KDV'li)", 'TOPTAN KÂR']]
        st.dataframe(wholesale_df_display.style.format({
            'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', "TOPTAN FİYAT (KDV'siz)": '{:,.2f} ₺', "TOPTAN FİYAT (KDV'li)": '{:,.2f} ₺', 'TOPTAN KÂR': '{:,.2f} ₺'
        }), use_container_width=True)

    st.markdown("---"); st.subheader("Adım 4: Kaydet ve Shopify'a Gönder")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Fiyatları Google E-Tablolar'a Kaydet", use_container_width=True):
            with st.spinner("Veriler Google E-Tablolar'a kaydediliyor..."):
                success, url = gsheets_manager.save_pricing_data_to_gsheets(main_df_display, discount_df_display, wholesale_df_display)
            if success: st.success(f"Veriler başarıyla kaydedildi! [E-Tabloyu Görüntüle]({url})")
    
    with col2:
        update_choice = st.selectbox("Hangi Fiyat Listesini Göndermek İstersiniz?", ["Ana Fiyatlar", "İndirimli Fiyatlar"])
        if st.button(f"🚀 {update_choice} Shopify'a Gönder", use_container_width=True, type="primary"):
            with st.spinner("Varyant fiyatları hazırlanıyor ve Shopify ile eşleştiriliyor..."):
                shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                
                if update_choice == "Ana Fiyatlar":
                    prices_to_apply = df[['MODEL KODU', 'NIHAI_SATIS_FIYATI']].rename(columns={'MODEL KODU': 'base_sku'})
                    df_to_send = pd.merge(st.session_state.df_variants, prices_to_apply, on='base_sku', how='left')
                    price_col, compare_at_price_col = 'NIHAI_SATIS_FIYATI', None
                else: 
                    prices_to_apply = retail_df[['MODEL KODU', 'NIHAI_SATIS_FIYATI', 'İNDİRİMLİ SATIŞ FİYATI']].rename(columns={'MODEL KODU': 'base_sku'})
                    df_to_send = pd.merge(st.session_state.df_variants, prices_to_apply, on='base_sku', how='left')
                    price_col, compare_at_price_col = 'İNDİRİMLİ SATIŞ FİYATI', 'NIHAI_SATIS_FIYATI'

                skus_to_update = df_to_send['MODEL KODU'].dropna().astype(str).tolist()
                variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)
                
                updates = []
                for _, row in df_to_send.iterrows():
                    sku = str(row['MODEL KODU'])
                    if sku in variant_map:
                        payload = {"variant_id": variant_map[sku], "price": f"{row[price_col]:.2f}"}
                        if compare_at_price_col and row[compare_at_price_col] is not None:
                            payload["compare_at_price"] = f"{row[compare_at_price_col]:.2f}"
                        else:
                            payload["compare_at_price"] = None
                        updates.append(payload)

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