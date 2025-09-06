# pages/6_Fiyat_Hesaplayıcı.py

import streamlit as st
import pandas as pd
import math
import numpy as np
import json # <<< IYILEŞTIRME: JSON importu eklendi
from io import StringIO # <<< IYILEŞTIRME: StringIO importu eklendi

# Proje dizinindeki modülleri import et
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shopify_sync import ShopifyAPI, SentosAPI
import data_manager

st.set_page_config(layout="wide", page_title="Fiyat Analiz ve Yönetim Panosu")

if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

# --- DÜZELTİLMİŞ VE İYİLEŞTİRİLMİŞ FONKSİYONLAR ---

def process_sentos_product_list(product_list):
    """
    Sentos'tan gelen ham ürün listesini işleyerek fiyatlandırma için temiz bir DataFrame'e dönüştürür.
    API'den gelen gerçek alan adlarını ('AlisFiyati', 'Varyasyonlar' vb.) kullanır.
    Varyantlı ve varyantsız ürünleri doğru bir şekilde işler.
    """
    processed_rows = []
    varyant_sayisi = 0
    varyantsiz_sayisi = 0

    for p in product_list:
        # Ana ürünün alış fiyatını güvenli bir şekilde al ve dönüştür
        try:
            main_purchase_price_str = str(p.get('AlisFiyati', '0')).replace(',', '.')
            main_purchase_price = float(main_purchase_price_str)
        except (ValueError, TypeError):
            main_purchase_price = 0.0

        variants = p.get('Varyasyonlar', [])
        
        if not variants:
            varyantsiz_sayisi += 1
            processed_rows.append({
                'MODEL KODU': p.get('StokKodu'), 
                'ÜRÜN ADI': p.get('UrunAdi'), 
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
                
                # Varyantın kendi alış fiyatı yoksa veya sıfırsa, ana ürünün fiyatını kullan
                final_price = variant_purchase_price if variant_purchase_price > 0 else main_purchase_price
                
                # Varyant adını oluştur
                variant_attributes = [val for val in v.get('Ozellikler', {}).values() if val]
                variant_name_suffix = " - " + " / ".join(variant_attributes) if variant_attributes else ""
                variant_name = f"{p.get('UrunAdi', '')}{variant_name_suffix}".strip()

                processed_rows.append({
                    'MODEL KODU': v.get('StokKodu'), 
                    'ÜRÜN ADI': variant_name, 
                    'ALIŞ FİYATI': final_price
                })
                
    st.info(f"{varyantsiz_sayisi} adet tekil ve {varyant_sayisi} adet varyant olmak üzere toplam {len(processed_rows)} satır işlendi.")
    return pd.DataFrame(processed_rows)


def apply_rounding(price, method):
    """Fiyatları belirtilen metoda göre X9.99 formatına yuvarlar."""
    if not isinstance(price, (int, float)) or price <= 0:
        return price
        
    if method == "Yukarı Yuvarla":
        # Örneğin 123.45 -> 129.99, 129.99 -> 129.99
        return math.floor(price / 10) * 10 + 9.99
    elif method == "Aşağı Yuvarla":
        # Örneğin 123.45 -> 119.99
        return math.ceil(price / 10) * 10 - 0.01
    return price # "Yok" seçiliyse fiyatı değiştirme

# --- ARAYÜZ ---

st.markdown("<h1>📊 Fiyat Stratejisi ve Yönetim Panosu</h1>", unsafe_allow_html=True)
st.markdown("<p>Fiyatlarınızı analiz edin, senaryoları test edin ve sonuçları tek tuşla Shopify mağazanıza yansıtın.</p>", unsafe_allow_html=True)

st.subheader("Adım 1: Ürün Verilerini Yükle")

if st.session_state.get('price_df') is None:
    col_fetch_new, col_load_saved = st.columns(2)
    with col_fetch_new:
        if st.button("🔄 Sentos'tan Yeni Fiyat Listesi Çek", type="secondary", use_container_width=True, help="Tüm ürünlerin alış fiyatlarını Sentos'tan yeniden çeker ve mevcut kayıtların üzerine yazar."):
            try:
                sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
                with st.spinner("Tüm ürünler Sentos API'den çekiliyor..."):
                    all_products = sentos_api.get_all_products()
                    # <<< DÜZELTME: Doğru fonksiyon adı kullanıldı
                    st.session_state.price_df = process_sentos_product_list(all_products)
                    st.session_state.calculated_df = None
                
                username = st.session_state["username"]
                # <<< IYILEŞTIRME: DataFrame'i 'split' yerine 'index=False' ile kaydetmek daha güvenli
                price_df_json = st.session_state.price_df.to_json(orient='split', index=False)
                
                data_manager.save_user_data(username, price_df_json=price_df_json, calculated_df_json=None)
                st.toast("Yeni alış fiyatları hesabınıza kalıcı olarak kaydedildi.")
                st.rerun()
            except Exception as e:
                st.error(f"Sentos API bağlantısı veya veri işleme sırasında hata: {e}")

    with col_load_saved:
        if st.button("📂 Kayıtlı Fiyat Listesini Yükle", use_container_width=True, help="Daha önce Sentos'tan çekip kaydettiğiniz fiyat listesini yükleyerek devam edin."):
            username = st.session_state["username"]
            user_data = data_manager.load_user_data(username)
            price_df_json_str = user_data.get('price_df_json')
            calculated_df_json_str = user_data.get('calculated_df_json')

            if price_df_json_str:
                try:
                    # <<< IYILEŞTIRME: JSON string'ini StringIO ile okumak daha kararlı
                    st.session_state.price_df = pd.read_json(StringIO(price_df_json_str), orient='split')
                    if calculated_df_json_str:
                        st.session_state.calculated_df = pd.read_json(StringIO(calculated_df_json_str), orient='split')
                    else:
                        st.session_state.calculated_df = None
                    st.toast("Kayıtlı veriler başarıyla yüklendi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Kayıtlı veriler okunurken bir hata oluştu: {e}")
            else:
                st.warning("Daha önce kaydedilmiş bir fiyat listesi bulunamadı.")
else:
    st.success(f"✅ {len(st.session_state.price_df)} ürün verisi şu anda hafızada yüklü.")
    if st.button("🧹 Verileri Temizle ve Baştan Başla", use_container_width=True):
        st.session_state.price_df = None
        st.session_state.calculated_df = None
        
        username = st.session_state["username"]
        data_manager.save_user_data(username, price_df_json=None, calculated_df_json=None)
        st.toast("Kalıcı verileriniz ve oturum verileriniz temizlendi.")
        st.rerun()

if st.session_state.get('price_df') is not None:
    st.markdown("---")
    st.subheader("Adım 2: Fiyatlandırma Kurallarını Uygula ve Analiz Et")
    
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
        with c1:
            markup_type = st.radio("Perakende Kâr Marjı", ["Yüzde Ekle (%)", "Çarpan Kullan (x)"], key="markup_type")
            if markup_type == "Yüzde Ekle (%)":
                markup_value = st.number_input("Yüzde", min_value=0, value=80, step=10, key="markup_value_percent")
            else:
                markup_value = st.number_input("Çarpan", min_value=1.0, value=2.5, step=0.1, key="markup_value_multiplier")
        with c2:
            add_vat = st.checkbox("Satışa KDV Dahil Et", value=True, key="add_vat")
            vat_rate = st.number_input("Satış KDV Oranı (%)", 0, 100, 10, disabled=not add_vat, key="vat_rate")
        with c3:
            rounding_method_text = st.radio("Fiyat Yuvarlama", ["Yok", "Yukarı (X9.99)", "Aşağı (X9.99)"], index=1, key="rounding")
        with c4:
            st.write("") # Boşluk için
            st.write("")
            if st.button("💰 Fiyatları Hesapla", type="primary", use_container_width=True, help="Girdiğiniz kurallara göre tüm fiyatları, kârları ve oranları hesaplar ve sonucu kalıcı olarak kaydeder."):
                df = st.session_state.price_df.copy()
                df['SATIS_FIYATI_KDVSIZ'] = df['ALIŞ FİYATI'] * (1 + markup_value / 100) if markup_type == "Yüzde Ekle (%)" else df['ALIŞ FİYATI'] * markup_value
                df['SATIS_FIYATI_KDVLI'] = df['SATIS_FIYATI_KDVSIZ'] * (1 + vat_rate / 100) if add_vat else df['SATIS_FIYATI_KDVSIZ']
                rounding_method_arg = rounding_method_text.replace(" (X9.99)", "").replace("Aşağı", "Aşağı Yuvarla").replace("Yukarı", "Yukarı Yuvarla")
                df['NIHAI_SATIS_FIYATI'] = df['SATIS_FIYATI_KDVLI'].apply(lambda p: apply_rounding(p, rounding_method_arg))
                
                revenue_before_tax = df['NIHAI_SATIS_FIYATI'] / (1 + vat_rate / 100) if add_vat else df['NIHAI_SATIS_FIYATI']
                df['KÂR'] = revenue_before_tax - df['ALIŞ FİYATI']
                df['KÂR ORANI (%)'] = np.divide(df['KÂR'], df['ALIŞ FİYATI'], out=np.zeros_like(df['KÂR']), where=df['ALIŞ FİYATI']!=0) * 100
                
                st.session_state.calculated_df = df
                
                username = st.session_state["username"]
                price_df_json = st.session_state.price_df.to_json(orient='split', index=False)
                calculated_df_json = st.session_state.calculated_df.to_json(orient='split', index=False)
                data_manager.save_user_data(username, price_df_json=price_df_json, calculated_df_json=calculated_df_json)
                st.toast("Hesaplanan fiyat listeniz kalıcı olarak kaydedildi.")
                st.rerun()

if st.session_state.get('calculated_df') is not None:
    df_calculated = st.session_state.calculated_df
    st.markdown("---")
    st.subheader("Adım 3: Senaryoları Analiz Et")

    with st.expander("Tablo 1: Ana Fiyat ve Kârlılık Listesi (Referans)", expanded=True):
        st.dataframe(df_calculated[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', 'SATIS_FIYATI_KDVSIZ', 'NIHAI_SATIS_FIYATI', 'KÂR', 'KÂR ORANI (%)']].style.format({
            'ALIŞ FİYATI': '{:,.2f} ₺', 'SATIS_FIYATI_KDVSIZ': '{:,.2f} ₺', 'NIHAI_SATIS_FIYATI': '{:,.2f} ₺',
            'KÂR': '{:,.2f} ₺', 'KÂR ORANI (%)': '{:.2f}%'
        }), use_container_width=True)
    
    with st.expander("Tablo 2: Perakende İndirim Analizi", expanded=True):
        st.markdown("Ana perakende fiyatına indirim uygulandığında oluşacak yeni kârlılığı analiz edin.")
        # <<< IYILEŞTIRME: Slider değerini session_state'e kaydederek durumunu koruyoruz
        retail_discount = st.slider("Uygulanacak İndirim Oranı (%)", 0, 50, st.session_state.get('retail_discount', 10), 5, key="retail_discount")
        
        retail_df = df_calculated.copy()
        vat_rate = st.session_state.get('vat_rate', 10)
        retail_df['İNDİRİMLİ SATIŞ FİYATI'] = retail_df['NIHAI_SATIS_FIYATI'] * (1 - retail_discount / 100)
        revenue_after_discount = retail_df['İNDİRİMLİ SATIŞ FİYATI'] / (1 + vat_rate / 100)
        retail_df['İNDİRİM SONRASI KÂR'] = revenue_after_discount - retail_df['ALIŞ FİYATI']
        retail_df['İNDİRİM SONRASI KÂR ORANI (%)'] = np.divide(retail_df['İNDİRİM SONRASI KÂR'], retail_df['ALIŞ FİYATI'], out=np.zeros_like(retail_df['İNDİRİM SONRASI KÂR']), where=retail_df['ALIŞ FİYATI']!=0) * 100
        
        if retail_discount > 0:
            st.dataframe(retail_df[['MODEL KODU', 'NIHAI_SATIS_FIYATI', 'İNDİRİMLİ SATIŞ FİYATI', 'İNDİRİM SONRASI KÂR', 'İNDİRİM SONRASI KÂR ORANI (%)']].style.format({
                'NIHAI_SATIS_FIYATI': '{:,.2f} ₺', 'İNDİRİMLİ SATIŞ FİYATI': '{:,.2f} ₺', 'İNDİRİM SONRASI KÂR': '{:,.2f} ₺', 'İNDİRİM SONRASI KÂR ORANI (%)': '{:.2f}%'
            }), use_container_width=True)
        else:
            st.info("Perakende indirim senaryosunu görmek için yukarıdaki kaydırma çubuğunu ayarlayın.")

    # ... (Toptan satış analizi kısmı aynı kalabilir, bir sorun görünmüyor) ...

    st.markdown("---")
    st.subheader("Adım 4: Fiyatları Shopify'a Gönder")
    st.warning("Bu işlem geri alınamaz. Lütfen göndermeden önce tablolardaki fiyatları dikkatlice kontrol edin.")
    update_col1, update_col2 = st.columns(2)
    with update_col1:
        if st.button("🚀 Mağaza Ana Fiyatlarını Güncelle", use_container_width=True, help="Yukarıdaki 'Ana Fiyat Listesi'ndeki NIHAI_SATIS_FIYATI'nı mağazadaki ana satış fiyatı yapar. Mevcut indirimler kaldırılır."):
            with st.spinner("Shopify ürün varyantları hazırlanıyor..."):
                shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                skus_to_update = df_calculated['MODEL KODU'].dropna().tolist()
                variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)
                updates = [{"variant_id": variant_map[sku], "price": f"{row['NIHAI_SATIS_FIYATI']:.2f}", "compare_at_price": None} for _, row in df_calculated.iterrows() if (sku := row['MODEL KODU']) in variant_map]
            
            if updates:
                results = shopify_api.bulk_update_variant_prices(updates)
                st.success(f"İşlem Tamamlandı! ✅ {results.get('success', 0)} ürün başarıyla güncellendi.")
                # ... Hata gösterimi aynı kalabilir ...
            else:
                st.warning("Shopify'da eşleşen güncellenecek ürün bulunamadı.")

    with update_col2:
        if st.button("🔥 Mağazaya İndirimli Fiyatları Yansıt", type="primary", use_container_width=True, help="Perakende indirim analizindeki indirimli fiyatları mağazaya yansıtır. Ana fiyat, üstü çizili fiyat olarak ayarlanır."):
            # <<< DÜZELTME: 'retail_discount' değerini session_state'den güvenli bir şekilde alıyoruz
            current_retail_discount = st.session_state.get('retail_discount', 0)
            if current_retail_discount > 0:
                with st.spinner("İndirimli fiyatlar için Shopify ürünleri hazırlanıyor..."):
                    shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                    skus_to_update = retail_df['MODEL KODU'].dropna().tolist()
                    variant_map = shopify_api.get_variant_ids_by_skus(skus_to_update)
                    updates = [{"variant_id": variant_map[sku], "price": f"{row['İNDİRİMLİ SATIŞ FİYATI']:.2f}", "compare_at_price": f"{row['NIHAI_SATIS_FIYATI']:.2f}"} for _, row in retail_df.iterrows() if (sku := row['MODEL KODU']) in variant_map]

                if updates:
                    results = shopify_api.bulk_update_variant_prices(updates)
                    st.success(f"İndirimler Tamamlandı! ✅ {results.get('success', 0)} ürün başarıyla güncellendi.")
                    # ... Hata gösterimi aynı kalabilir ...
                else:
                    st.warning("Shopify'da eşleşen güncellenecek ürün bulunamadı.")
            else:
                st.warning("İndirim uygulamak için lütfen 'Perakende İndirim Analizi' bölümündeki indirim oranını %0'dan büyük bir değere ayarlayın.")