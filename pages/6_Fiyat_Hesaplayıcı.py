import streamlit as st
import pandas as pd
import math
from io import BytesIO
import numpy as np

# Gerekli modülleri import ediyoruz
from shopify_sync import SentosAPI
import config_manager

# --- Sayfa Yapılandırması ve Güvenlik ---
st.set_page_config(layout="wide", page_title="Fiyat Analiz Panosu")

# Giriş kontrolü
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

# --- Yardımcı Fonksiyonlar ---
def process_product_list(product_list):
    processed_products = []
    for p in product_list:
        price_str = str(p.get('purchase_price', '0')).replace(',', '.')
        try:
            purchase_price = float(price_str)
        except (ValueError, TypeError):
            purchase_price = 0.0
        processed_products.append({
            'MODEL KODU': p.get('sku'), 'ÜRÜN ADI': p.get('name'), 'ALIŞ FİYATI': purchase_price
        })
    return pd.DataFrame(processed_products)

def apply_rounding(price, method):
    if method == "Yukarı Yuvarla":
        if price % 10 != 9.99 and price % 10 != 9:
            return math.floor(price / 10) * 10 + 9.99
        elif price % 1 == 0:
             return price - 0.01
        return price
    elif method == "Aşağı Yuvarla":
        return math.floor(price / 10) * 10 + 5.99
    return price

# --- Session State Başlatma (Giriş sayfasında zaten yapılıyor ama burada da olabilir) ---
if 'price_df' not in st.session_state: st.session_state.price_df = None
if 'calculated_df' not in st.session_state: st.session_state.calculated_df = None

# --- ARAYÜZ ---
st.markdown("<h1>📊 Fiyat Stratejisi ve Analiz Panosu</h1>", unsafe_allow_html=True)
st.markdown("<p>Bu pano ile temel perakende fiyatlarınızı oluşturabilir, ardından perakende ve toptan satış senaryolarını test ederek kârlılık analizleri yapabilirsiniz.</p>", unsafe_allow_html=True)

st.subheader("Adım 1: Ürün Verilerini Yükle ve Temel Fiyatları Hesapla")
col_load, col_calc = st.columns(2)
with col_load:
    if st.session_state.price_df is None:
        if st.button("🔄 Sentos'tan Alış Fiyatlarını Çek", type="secondary", use_container_width=True):
            status_placeholder = st.empty()
            def progress_callback(data): status_placeholder.text(f"⏳ {data.get('message', 'İşlem sürüyor...')}")
            try:
                sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret)
                all_products = sentos_api.get_all_products(progress_callback=progress_callback)
                st.session_state.price_df = process_product_list(all_products)
                st.session_state.calculated_df = None
                
                # --- Çekilen veriyi kalıcı olarak kaydet ---
                try:
                    username = st.session_state["username"]
                    price_df_json = st.session_state.price_df.to_json(orient='split')
                    # Yeni veri çekildiğinde eski hesaplanmış veriyi de temizle
                    config_manager.save_user_keys(
                        username,
                        price_df_json=price_df_json,
                        calculated_df_json="" 
                    )
                    st.toast("Alış fiyatları hesabınıza kalıcı olarak kaydedildi.")
                except Exception as e:
                    st.warning(f"Veriler kalıcı olarak kaydedilemedi: {e}")
                
                st.rerun()
            except Exception as e: st.error(f"API bağlantısı kurulamadı: {e}")
    else:
        st.success(f"✅ {len(st.session_state.price_df)} ürün verisi hafızaya yüklendi.")
        if st.button("🧹 Verileri Temizle ve Yeniden Başla", use_container_width=True):
            st.session_state.price_df = None
            st.session_state.calculated_df = None
            
            # --- Kalıcı verileri de temizle ---
            try:
                username = st.session_state["username"]
                config_manager.save_user_keys(
                    username,
                    price_df_json="", # Boş değer göndererek silinmesini sağlıyoruz
                    calculated_df_json=""
                )
                st.toast("Kalıcı verileriniz temizlendi.")
            except Exception as e:
                st.warning(f"Kalıcı veriler temizlenirken bir hata oluştu: {e}")
            
            st.rerun()

if st.session_state.price_df is not None:
    with st.container(border=True):
        # ... (Bu kısımda değişiklik yok)
        st.markdown("<h6>Temel Fiyatlandırma Kuralları</h6>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            markup_type = st.radio("Perakende Kâr Marjı", ["Yüzde Ekle (%)", "Çarpan Kullan (x)"])
            if markup_type == "Yüzde Ekle (%)": markup_value = st.selectbox("Yüzde", [50, 60, 70, 80, 100, 120], index=3)
            else: markup_value = st.selectbox("Çarpan", [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0], index=2)
        with c2:
            add_vat = st.checkbox("Satışa KDV Dahil Et", value=True)
            vat_rate = st.number_input("Satış KDV Oranı (%)", 0, 100, 20, disabled=not add_vat)
        with c3:
            rounding_method_text = st.radio("Fiyat Yuvarlama", ["Yok", "Yukarı (X,99)", "Aşağı (X,99)"], index=1)
    
    with col_calc:
        if st.button("💰 Temel Fiyat Listesini Oluştur ve Kaydet", type="primary", use_container_width=True):
            df = st.session_state.price_df.copy()
            df['SATIS_FIYATI_KDVSIZ'] = df['ALIŞ FİYATI'] * (1 + markup_value / 100) if markup_type == "Yüzde Ekle (%)" else df['ALIŞ FİYATI'] * markup_value
            df['SATIS_FIYATI_KDVLI'] = df['SATIS_FIYATI_KDVSIZ'] * (1 + vat_rate / 100) if add_vat else df['SATIS_FIYATI_KDVSIZ']
            rounding_method_arg = rounding_method_text.replace(" (X,99)", "").replace("Aşağı", "Aşağı Yuvarla").replace("Yukarı", "Yukarı Yuvarla")
            df['NIHAI_SATIS_FIYATI'] = df['SATIS_FIYATI_KDVLI'].apply(lambda p: apply_rounding(p, rounding_method_arg))
            profit_vat_divisor = 1 + (10 / 100)
            revenue_before_tax = df['NIHAI_SATIS_FIYATI'] / profit_vat_divisor
            df['KÂR'] = revenue_before_tax - df['ALIŞ FİYATI']
            df['KÂR ORANI (%)'] = np.divide(df['KÂR'], revenue_before_tax, out=np.zeros_like(df['KÂR']), where=revenue_before_tax!=0) * 100
            st.session_state.calculated_df = df
            st.success("Temel fiyat listesi oluşturuldu ve hafızaya kaydedildi.")
            
            # --- HESAPLANAN VERİYİ KALICI OLARAK KAYDET ---
            try:
                username = st.session_state["username"]
                # Her ihtimale karşı price_df'i de tekrar kaydet
                price_df_json = st.session_state.price_df.to_json(orient='split')
                calculated_df_json = st.session_state.calculated_df.to_json(orient='split')
                config_manager.save_user_keys(
                    username,
                    price_df_json=price_df_json,
                    calculated_df_json=calculated_df_json
                )
                st.toast("Hesaplanan fiyat listeniz hesabınıza kalıcı olarak kaydedildi.")
            except Exception as e:
                st.warning(f"Hesaplanan veriler kalıcı olarak kaydedilemedi: {e}")

if st.session_state.calculated_df is not None:
    # ... (Sayfanın geri kalan analiz kısmı olduğu gibi kalabilir, değişiklik yok)
    st.markdown("---")
    st.subheader("Adım 2: Senaryoları Analiz Et")

    with st.expander("Tablo 1: Ana Fiyat ve Kârlılık Listesi (Referans)", expanded=True):
        main_format_dict = {
            'ALIŞ FİYATI': '{:,.2f} ₺', 'SATIS_FIYATI_KDVSIZ': '{:,.2f} ₺', 'NIHAI_SATIS_FIYATI': '{:,.2f} ₺',
            'KÂR': '{:,.2f} ₺', 'KÂR ORANI (%)': '{:.2f}%'
        }
        st.dataframe(st.session_state.calculated_df.style.format(main_format_dict), use_container_width=True)
    
    with st.expander("Tablo 2: Perakende İndirim Analizi", expanded=True):
        st.markdown("Ana perakende fiyatına indirim uygulandığında oluşacak yeni kârlılığı analiz edin.")
        retail_discount = st.slider("Uygulanacak İndirim Oranı (%)", 0, 50, 10, 5, key="retail_slider")
        
        if retail_discount > 0:
            retail_df = st.session_state.calculated_df.copy()
            retail_df['İNDİRİM ORANI (%)'] = retail_discount
            retail_df['İNDİRİMLİ SATIŞ FİYATI'] = retail_df['NIHAI_SATIS_FIYATI'] * (1 - retail_discount / 100)
            profit_vat_divisor = 1 + (10 / 100)
            revenue_after_discount = retail_df['İNDİRİMLİ SATIŞ FİYATI'] / profit_vat_divisor
            retail_df['İNDİRİM SONRASI KÂR'] = revenue_after_discount - retail_df['ALIŞ FİYATI']
            retail_df['İNDİRİM SONRASI KÂR ORANI (%)'] = np.divide(retail_df['İNDİRİM SONRASI KÂR'], revenue_after_discount, out=np.zeros_like(retail_df['İNDİRİM SONRASI KÂR']), where=revenue_after_discount!=0) * 100
            
            retail_cols_to_show = ['MODEL KODU', 'ÜRÜN ADI', 'NIHAI_SATIS_FIYATI', 'İNDİRİM ORANI (%)', 'İNDİRİMLİ SATIŞ FİYATI', 'İNDİRİM SONRASI KÂR', 'İNDİRİM SONRASI KÂR ORANI (%)']
            retail_display_df = retail_df[retail_cols_to_show]
            
            retail_format_dict = {
                'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', 'İNDİRİM ORANI (%)': '{:.0f}%', 'İNDİRİMLİ SATIŞ FİYATI': '{:,.2f} ₺',
                'İNDİRİM SONRASI KÂR': '{:,.2f} ₺', 'İNDİRİM SONRASI KÂR ORANI (%)': '{:.2f}%'
            }
            st.dataframe(retail_display_df.style.format(retail_format_dict), use_container_width=True)
        else:
            st.info("Perakende indirim senaryosunu görmek için yukarıdaki kaydırma çubuğunu ayarlayın.")

    with st.expander("Tablo 3: Toptan Satış Fiyat Analizi", expanded=True):
        st.markdown("Toptan satış fiyatını farklı yöntemlerle belirleyip kârlılığını analiz edin.")
        wholesale_method = st.radio("Toptan Fiyat Hesaplama Yöntemi", ('Alış Fiyatı Üzerinden Çarpanla', 'Perakende Fiyatı Üzerinden İndirimle'), horizontal=True)
        
        wholesale_df = st.session_state.calculated_df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', 'NIHAI_SATIS_FIYATI']].copy()
        
        if wholesale_method == 'Alış Fiyatı Üzerinden Çarpanla':
            ws_multiplier = st.number_input("Toptan Çarpanı", 1.0, 5.0, 1.8, 0.1)
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = wholesale_df["ALIŞ FİYATI"] * ws_multiplier
        else:
            ws_discount = st.slider("Perakende Fiyatından İndirim (%)", 10, 70, 40, 5)
            sales_vat_divisor = 1 + (vat_rate / 100) if add_vat else 1
            wholesale_df["TOPTAN FİYAT (KDV'siz)"] = (wholesale_df["NIHAI_SATIS_FIYATI"] / sales_vat_divisor) * (1 - ws_discount / 100)
            
        wholesale_df['TOPTAN KÂR'] = wholesale_df["TOPTAN FİYAT (KDV'siz)"] - wholesale_df["ALIŞ FİYATI"]
        wholesale_df['TOPTAN KÂR ORANI (%)'] = np.divide(wholesale_df['TOPTAN KÂR'], wholesale_df["TOPTAN FİYAT (KDV'siz)"], out=np.zeros_like(wholesale_df['TOPTAN KÂR']), where=wholesale_df["TOPTAN FİYAT (KDV'siz)"]!=0) * 100
        
        wholesale_cols_to_show = ['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', "TOPTAN FİYAT (KDV'siz)", 'TOPTAN KÂR', 'TOPTAN KÂR ORANI (%)']
        wholesale_display_df = wholesale_df[wholesale_cols_to_show]

        wholesale_format_dict = {
            'ALIŞ FİYATI': '{:,.2f} ₺', "TOPTAN FİYAT (KDV'siz)": '{:,.2f} ₺', 'TOPTAN KÂR': '{:,.2f} ₺', 'TOPTAN KÂR ORANI (%)': '{:.2f}%'
        }
        st.dataframe(wholesale_display_df.style.format(wholesale_format_dict), use_container_width=True)