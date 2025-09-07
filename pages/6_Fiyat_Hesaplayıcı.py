# pages/6_Fiyat_Hesaplayıcı.py (API Anahtar İsimleri Düzeltilmiş Sürüm)

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

# <<< DÜZELTME BAŞLANGICI: Fonksiyon, shopify_sync.py ile uyumlu hale getirildi >>>
def process_sentos_product_list(product_list):
    """
    Sentos'tan gelen ham ürün listesini, uygulamanın genelinde kullanılan
    İngilizce anahtarlara ('name', 'sku', 'variants') göre işler.
    """
    processed_rows = []
    varyant_sayisi = 0
    varyantsiz_sayisi = 0

    for p in product_list:
        try:
            # Alış fiyatı anahtarının 'AlisFiyati' olarak kaldığı varsayılıyor
            main_purchase_price_str = str(p.get('AlisFiyati', '0')).replace(',', '.')
            main_purchase_price = float(main_purchase_price_str)
        except (ValueError, TypeError):
            main_purchase_price = 0.0

        # Anahtar 'Varyasyonlar' yerine 'variants' olarak değiştirildi
        variants = p.get('variants', [])
        
        if not variants:
            varyantsiz_sayisi += 1
            processed_rows.append({
                'MODEL KODU': p.get('sku'),       # Anahtar 'StokKodu' yerine 'sku' oldu
                'ÜRÜN ADI': p.get('name'),         # Anahtar 'UrunAdi' yerine 'name' oldu
                'ALIŞ FİYATI': main_purchase_price
            })
        else:
            for v in variants:
                varyant_sayisi += 1
                try:
                    variant_price_str = str(v.get('AlisFiyati', '0')).replace(',', '.')
                    variant_purchase_price = float(variant_price_str) if variant_price_str else 0.0
                except (ValueError, TypeError):
                    variant_purchase_price = 0.0
                
                final_price = variant_purchase_price if variant_purchase_price > 0 else main_purchase_price
                
                # Varyant adı oluşturma mantığı shopify_sync.py'ye uyarlandı
                color = v.get('color', '').strip()
                model_data = v.get('model', '') # 'model' bedeni tutuyor
                size = (model_data.get('value', '') if isinstance(model_data, dict) else str(model_data)).strip()

                attributes = []
                if color: attributes.append(color)
                if size: attributes.append(size)
                
                suffix = " - " + " / ".join(attributes) if attributes else ""
                product_name = p.get('name', '') # Ana ürün adını al
                variant_name = f"{product_name}{suffix}".strip()

                processed_rows.append({
                    'MODEL KODU': v.get('sku'), 
                    'ÜRÜN ADI': variant_name, 
                    'ALIŞ FİYATI': final_price
                })
                
    st.info(f"{varyantsiz_sayisi} adet tekil ve {varyant_sayisi} adet varyant olmak üzere toplam {len(processed_rows)} satır işlendi.")
    return pd.DataFrame(processed_rows)
# <<< DÜZELTME SONU >>>


def apply_rounding(price, method):
    """Fiyat yuvarlama mantığını uygular."""
    if method == "Yukarı Yuvarla":
        if price % 10 != 9.99 and price % 10 != 9: return math.floor(price / 10) * 10 + 9.99
        elif price % 1 == 0: return price - 0.01
        return price
    elif method == "Aşağı Yuvarla":
        return math.floor(price / 10) * 10 - 0.01 if price > 10 else 9.99
    return price

# --- Session State Başlatma ---
if 'calculated_df' not in st.session_state: st.session_state.calculated_df = None
if 'price_df' not in st.session_state: st.session_state.price_df = None

# --- ARAYÜZ ---
st.markdown("""
<div class="main-header">
    <h1>📊 Fiyat Stratejisi Panosu</h1>
    <p>Fiyat senaryoları oluşturun, Google E-Tablolar'a kaydedin ve Shopify'a gönderin.</p>
</div>
""", unsafe_allow_html=True)

# Adım 1: Veri Yükleme
st.subheader("Adım 1: Ürün Verilerini Yükle")
if st.session_state.calculated_df is None and st.session_state.price_df is None:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Sentos'tan Yeni Fiyat Listesi Çek", use_container_width=True):
            try:
                sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
                
                progress_bar = st.progress(0, text="Sentos API'ye bağlanılıyor...")
                
                def progress_callback(update):
                    progress = update.get('progress', 0)
                    message = update.get('message', 'Veriler işleniyor...')
                    progress_bar.progress(progress / 100.0, text=message)

                all_products = sentos_api.get_all_products(progress_callback=progress_callback)
                progress_bar.progress(100, text="Veriler işleniyor...")

                if not all_products:
                    st.error("❌ Sentos API'den hiç ürün verisi gelmedi. Lütfen API ayarlarınızı kontrol edin.")
                    progress_bar.empty()
                else:
                    st.session_state.price_df = process_sentos_product_list(all_products)
                    progress_bar.empty()
                    if st.session_state.price_df.empty or st.session_state.price_df['MODEL KODU'].isnull().all():
                         st.warning("Veri işlendi ancak model kodu, ürün adı gibi temel bilgiler alınamadı. Lütfen API yanıtını ve anahtar isimlerini kontrol edin.")
                    else:
                         st.toast(f"{len(st.session_state.price_df)} ürün için alış fiyatları başarıyla çekildi."); st.rerun()

            except Exception as e: 
                st.error(f"API hatası: {e}")
                if 'progress_bar' in locals():
                    progress_bar.empty()
    with col2:
        if st.button("📂 Kayıtlı Fiyat Listesini Yükle (Google Sheets)", use_container_width=True):
            with st.spinner("Google E-Tablolardan veriler yükleniyor..."):
                loaded_df = gsheets_manager.load_pricing_data_from_gsheets()
            if loaded_df is not None:
                st.session_state.calculated_df = loaded_df
                st.toast("Kayıtlı fiyat listesi başarıyla yüklendi!"); st.rerun()
else:
    source = "hesaplanan (Google Sheets)" if st.session_state.calculated_df is not None else "ham (Sentos)"
    count = len(st.session_state.calculated_df if st.session_state.calculated_df is not None else st.session_state.price_df)
    st.success(f"✅ {count} ürün verisi ({source}) hafızada yüklü.")
    if st.button("🧹 Verileri Temizle ve Baştan Başla", use_container_width=True):
        st.session_state.price_df = None; st.session_state.calculated_df = None; st.rerun()

if st.session_state.price_df is not None or st.session_state.calculated_df is not None:
    st.markdown("---"); st.subheader("Adım 2: Fiyatlandırma Kurallarını Uygula")
    base_df_source = st.session_state.price_df if st.session_state.price_df is not None else st.session_state.calculated_df
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
        markup_type = c1.radio("Kâr Marjı Tipi", ["Yüzde Ekle (%)", "Çarpan Kullan (x)"], key="markup_type")
        markup_value = c1.number_input("Değer", min_value=0.0, value=100.0 if markup_type == "Yüzde Ekle (%)" else 2.5, step=0.1, key="markup_value")
        add_vat = c2.checkbox("Satışa KDV Dahil Et", value=True, key="add_vat")
        vat_rate = c2.number_input("KDV Oranı (%)", 0, 100, 10, disabled=not add_vat, key="vat_rate")
        rounding_method_text = c3.radio("Fiyat Yuvarlama", ["Yok", "Yukarı (X9.99)", "Aşağı (X9.99)"], index=1, key="rounding")
        
        if c4.button("💰 Fiyatları Hesapla", type="primary", use_container_width=True):
            df = st.session_state.price_df.copy() if st.session_state.price_df is not None else st.session_state.calculated_df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI']].copy()
            
            df['SATIS_FIYATI_KDVSIZ'] = df['ALIŞ FİYATI'] * (1 + markup_value / 100) if markup_type == "Yüzde Ekle (%)" else df['ALIŞ FİYATI'] * markup_value
            df['SATIS_FIYATI_KDVLI'] = df['SATIS_FIYATI_KDVSIZ'] * (1 + vat_rate / 100) if add_vat else df['SATIS_FIYATI_KDVSIZ']
            
            rounding_method_arg = rounding_method_text.replace(" (X9.99)", "").replace("Aşağı", "Aşağı Yuvarla").replace("Yukarı", "Yukarı Yuvarla")
            df['NIHAI_SATIS_FIYATI'] = df['SATIS_FIYATI_KDVLI'].apply(lambda p: apply_rounding(p, rounding_method_arg))

            revenue = df['NIHAI_SATIS_FIYATI'] / (1 + vat_rate / 100) if add_vat else df['NIHAI_SATIS_FIYATI']
            df['KÂR'] = revenue - df['ALIŞ FİYATI']
            df['KÂR ORANI (%)'] = np.divide(df['KÂR'], df['ALIŞ FİYATI'], out=np.zeros_like(df['KÂR']), where=df['ALIŞ FİYATI']!=0) * 100
            st.session_state.calculated_df = df
            st.session_state.price_df = None
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
    
    with st.expander("Tablo 2: Perakende İndirim Analizi"):
        retail_discount = st.slider("İndirim Oranı (%)", 0, 50, st.session_state.get('retail_discount', 10), 5, key="retail_discount")
        retail_df = df.copy()
        current_vat_rate = st.session_state.get('vat_rate', 10) 
        retail_df['İNDİRİM ORANI (%)'] = retail_discount
        retail_df['İNDİRİMLİ SATIŞ FİYATI'] = retail_df['NIHAI_SATIS_FIYATI'] * (1 - retail_discount / 100)
        revenue_after_discount = retail_df['İNDİRİMLİ SATIŞ FİYATI'] / (1 + current_vat_rate / 100)
        retail_df['İNDİRİM SONRASI KÂR'] = revenue_after_discount - retail_df['ALIŞ FİYATI']
        retail_df['İNDİRİM SONRASI KÂR ORANI (%)'] = np.divide(retail_df['İNDİRİM SONRASI KÂR'], retail_df['ALIŞ FİYATI'], out=np.zeros_like(retail_df['İNDİRİM SONRASI KÂR']), where=retail_df['ALIŞ FİYATI']!=0) * 100
        discount_df_display = retail_df[['MODEL KODU', 'ÜRÜN ADI', 'NIHAI_SATIS_FIYATI', 'İNDİRİM ORANI (%)', 'İNDİRİMLİ SATIŞ FİYATI', 'İNDİRİM SONRASI KÂR', 'İNDİRİM SONRASI KÂR ORANI (%)']]
        st.dataframe(discount_df_display.style.format({
            'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', 'İNDİRİM ORANI (%)': '{:.0f}%', 'İNDİRİMLİ SATIŞ FİYATI': '{:,.2f} ₺',
            'İNDİRİM SONRASI KÂR': '{:,.2f} ₺', 'İNDİRİM SONRASI KÂR ORANI (%)': '{:.2f}%'
        }), use_container_width=True)

    with st.expander("Tablo 3: Toptan Satış Fiyat Analizi"):
        wholesale_df = df.copy()
        current_vat_rate = st.session_state.get('vat_rate', 10)
        wholesale_method = st.radio("Toptan Fiyat Hesaplama Yöntemi", ('Alış Fiyatı Üzerinden Çarpanla', 'Perakende Fiyatı Üzerinden İndirimle'), horizontal=True, key="ws_method")
        if wholesale_method == 'Alış Fiyatı Üzerinden Çarpanla':
            ws_multiplier = st.number_input("Toptan Çarpanı", 1.0, 5.0, 1.8, 0.1)
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = wholesale_df["ALIŞ FİYATI"] * ws_multiplier
        else:
            ws_discount = st.slider("Perakende Fiyatından İndirim (%)", 10, 70, 40, 5, key="ws_discount")
            sales_vat_divisor = 1 + (current_vat_rate / 100)
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = (wholesale_df["NIHAI_SATIS_FIYATI"] / sales_vat_divisor) * (1 - ws_discount / 100)
        
        wholesale_df["TOPTAN FİYAT (KDV'li)"] = wholesale_df["TOPTAN FİYAT (KDV'siz)"] * (1 + current_vat_rate / 100)
        wholesale_df['TOPTAN KÂR'] = wholesale_df["TOPTAN FİYAT (KDV'siz)"] - wholesale_df["ALIŞ FİYATI"]
        wholesale_df['PERAKENDEDEN İSKONTO (%)'] = (1 - (wholesale_df["TOPTAN FİYAT (KDV'li)"] / wholesale_df['NIHAI_SATIS_FIYATI'])) * 100
        wholesale_df_display = wholesale_df[['MODEL KODU', 'ÜRÜN ADI', 'NIHAI_SATIS_FIYATI', "TOPTAN FİYAT (KDV'siz)", "TOPTAN FİYAT (KDV'li)", 'TOPTAN KÂR', 'PERAKENDEDEN İSKONTO (%)']]
        st.dataframe(wholesale_df_display.style.format({
            'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', "TOPTAN FİYAT (KDV'siz)": '{:,.2f} ₺', "TOPTAN FİYAT (KDV'li)": '{:,.2f} ₺',
            'TOPTAN KÂR': '{:,.2f} ₺', 'PERAKENDEDEN İSKONTO (%)': '{:.2f}%'
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
            shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            
            if update_choice == "Ana Fiyatlar":
                df_to_send = main_df_display; price_col = 'NIHAI_SATIS_FIYATI'; compare_at_price_col = None
            else:
                df_to_send = discount_df_display; price_col = 'İNDİRİMLİ SATIŞ FİYATI'; compare_at_price_col = 'NIHAI_SATIS_FIYATI'
            st.info(f"{len(df_to_send)} ürünün fiyatı Shopify'a güncelleniyor...")
            with st.spinner("Varyant ID'leri alınıyor ve güncellemeler hazırlanıyor..."):
                skus_to_update = df_to_send['MODEL KODU'].dropna().tolist()
                variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)
                updates = []
                for _, row in df_to_send.iterrows():
                    sku = row['MODEL KODU']
                    if sku in variant_map:
                        update_payload = {"variant_id": variant_map[sku], "price": f"{row[price_col]:.2f}"}
                        if compare_at_price_col: update_payload["compare_at_price"] = f"{row[compare_at_price_col]:.2f}"
                        else: update_payload["compare_at_price"] = None
                        updates.append(update_payload)
            if updates:
                with st.spinner(f"{len(updates)} ürün fiyatı güncelleniyor..."):
                    results = shopify_api.bulk_update_variant_prices(updates)
                st.success(f"İşlem Tamamlandı! ✅ {results.get('success', 0)} ürün başarıyla güncellendi.")
                if results.get('failed', 0) > 0:
                    st.error(f"❌ {results.get('failed', 0)} ürün güncellenirken hata oluştu.")
                    with st.expander("Hata Detayları"): st.json(results.get('errors', []))
            else:
                st.warning("Shopify'da eşleşen güncellenecek ürün bulunamadı.")