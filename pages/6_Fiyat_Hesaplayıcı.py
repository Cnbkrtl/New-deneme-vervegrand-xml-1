# pages/6_Fiyat_Hesaplayıcı.py (Son Hatalar Giderilmiş Sürüm)

import streamlit as st
import pandas as pd
import math
import numpy as np
import json
from io import StringIO
import sys
import os
import queue
import threading
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from connectors.shopify_api import ShopifyAPI
from connectors.sentos_api import SentosAPI
from operations.price_sync import send_prices_to_shopify
from gsheets_manager import load_pricing_data_from_gsheets, save_pricing_data_to_gsheets

# --- Sayfa Kurulumu ve Kontroller ---
def load_css():
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
def process_sentos_data(product_list):
    all_variants_rows = []
    main_products_rows = []
    for p in product_list:
        main_sku = p.get('sku')
        main_name = p.get('name')
        try:
            main_price_str = str(p.get('purchase_price') or p.get('AlisFiyati') or '0').replace(',', '.')
            main_purchase_price = float(main_price_str)
        except (ValueError, TypeError):
            main_purchase_price = 0.0
        main_products_rows.append({
            'MODEL KODU': main_sku, 'ÜRÜN ADI': main_name, 'ALIŞ FİYATI': main_purchase_price
        })
        variants = p.get('variants', [])
        if not variants:
            all_variants_rows.append({
                'base_sku': main_sku, 'MODEL KODU': main_sku,
                'ÜRÜN ADI': main_name, 'ALIŞ FİYATI': main_purchase_price
            })
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
                    'base_sku': main_sku, 'MODEL KODU': v.get('sku'),
                    'ÜRÜN ADI': variant_name, 'ALIŞ FİYATI': final_price
                })
    df_variants = pd.DataFrame(all_variants_rows)
    df_main_products = pd.DataFrame(main_products_rows).drop_duplicates(subset=['MODEL KODU'])
    return df_variants, df_main_products

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
st.session_state.setdefault('retail_df', None)
st.session_state.setdefault('sync_progress_queue', queue.Queue())
st.session_state.setdefault('sync_log_list', [])

# --- ARAYÜZ (Bu bölümde değişiklik yok) ---
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
                    progress_bar.empty()
                    st.toast(f"Veriler Sentos'tan çekildi. {len(df_main)} ana ürün ve {len(df_variants)} varyant hafızaya alındı.")
                    st.rerun()
            except Exception as e: 
                if 'progress_bar' in locals():
                    progress_bar.empty()
                st.error(f"API hatası: {e}")
    
    with col2:
        if st.button("📄 Kayıtlı Veriyi G-Sheets'ten Yükle", use_container_width=True):
            with st.spinner("Google E-Tablolardan veriler yükleniyor..."):
                loaded_df = load_pricing_data_from_gsheets()
            if loaded_df is not None and not loaded_df.empty:
                st.session_state.calculated_df = loaded_df
                st.session_state.df_for_display = loaded_df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI']]
                st.session_state.df_variants = None
                st.toast("Veriler Google E-Tablolar'dan yüklendi.")
                st.rerun()
            else:
                st.warning("Google E-Tablolar'dan veri yüklenemedi veya dosya boş.")
else:
    main_count = len(st.session_state.df_for_display)
    variants_df = st.session_state.get('df_variants')
    variants_count = len(variants_df) if variants_df is not None and not variants_df.empty else 0
    message = f"✅ {main_count} ana ürün verisi hafızada yüklü."
    if variants_count > 0:
        message += f" | 📦 **{variants_count} varyant verisi** Shopify'a gönderim için hazır."
    st.success(message)
    if st.button("🧹 Verileri Temizle ve Baştan Başla", use_container_width=True):
        st.session_state.calculated_df = None
        st.session_state.df_for_display = None
        st.session_state.df_variants = None
        st.session_state.sync_log_list = []
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
            st.toast("Fiyatlar hesaplandı.")
            st.rerun()

if st.session_state.calculated_df is not None:
    st.markdown("---"); st.subheader("Adım 3: Senaryoları Analiz Et")
    df = st.session_state.calculated_df
    vat_rate = st.session_state.get('vat_rate', 10)
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
        st.session_state.retail_df = retail_df # Retail DF'i session state'e kaydet
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

    st.markdown("---")
    st.subheader("Adım 4: Kaydet ve Shopify'a Gönder")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Fiyatları Google E-Tablolar'a Kaydet", use_container_width=True):
            with st.spinner("Veriler Google E-Tablolar'a kaydediliyor..."):
                main_df = st.session_state.calculated_df[['MODEL KODU', 'ÜRÜN ADI', 'ALIŞ FİYATI', 'NIHAI_SATIS_FIYATI']]
                discount_df = st.session_state.retail_df[['MODEL KODU', 'ÜRÜN ADI', 'İNDİRİMLİ SATIŞ FİYATI']]
                wholesale_df = wholesale_df[['MODEL KODU', 'ÜRÜN ADI', "TOPTAN FİYAT (KDV'li)"]]
                success, url = save_pricing_data_to_gsheets(main_df, discount_df, wholesale_df)
            if success: 
                st.success(f"Veriler başarıyla kaydedildi! [E-Tabloyu Görüntüle]({url})")
    
    with col2:
        # Shopify güncelleme ayarları
        with st.expander("⚙️ Güncelleme Ayarları", expanded=False):
            col_a, col_b = st.columns(2)
            
            with col_a:
                worker_count = st.slider(
                    "🔧 Paralel Worker Sayısı",
                    min_value=1,
                    max_value=15,
                    value=10,
                    help="Daha fazla worker = daha hızlı güncelleme. Ancak çok fazla worker rate limit'e takılabilir."
                )
                
                batch_size = st.number_input(
                    "📦 Batch Boyutu",
                    min_value=100,
                    max_value=10000,
                    value=1000,
                    step=100,
                    help="Tek seferde kaç varyant güncellensin? Büyük batch'ler için daha fazla bellek gerekir."
                )
            
            with col_b:
                retry_count = st.number_input(
                    "🔄 Tekrar Deneme Sayısı",
                    min_value=1,
                    max_value=5,
                    value=3,
                    help="Hata durumunda kaç kez tekrar denensin?"
                )
                
                continue_from_last = st.checkbox(
                    "⏯️ Kaldığı yerden devam et",
                    value=False,
                    help="Önceki güncelleme yarıda kaldıysa, başarısız olanları tekrar dene"
                )
        
        update_choice = st.selectbox("Hangi Fiyat Listesini Göndermek İstersiniz?", ["Ana Fiyatlar", "İndirimli Fiyatlar"])
        
        # Devam et modunda önceki sonuçları göster
        if continue_from_last and 'last_update_results' in st.session_state:
            last_results = st.session_state.last_update_results
            st.info(f"""
            📊 Önceki güncelleme sonucu:
            - ✅ Başarılı: {last_results.get('success', 0)}
            - ❌ Başarısız: {last_results.get('failed', 0)}
            - 🔄 Tekrar denenecek: {last_results.get('failed', 0)} varyant
            """)
        
        if st.button(f"🚀 {update_choice} Shopify'a Gönder", use_container_width=True, type="primary"):
            if st.session_state.df_variants is None or st.session_state.df_variants.empty:
                st.error("HATA: Hafızada varyant verisi bulunamadı. Lütfen önce Sentos'tan veri çekin.")
                st.stop()
            
            st.session_state.sync_log_list = []
            progress_bar = st.progress(0, text="Güncelleme işlemi başlatılıyor...")
            log_placeholder = st.empty()
            stats_placeholder = st.empty()  # İstatistikler için
            
            def shopify_progress_callback(data):
                progress = data.get('progress', 0)
                message = data.get('message', 'İşleniyor...')
                log_detail = data.get('log_detail')
                stats = data.get('stats')
                
                if progress_bar:
                    progress_bar.progress(progress / 100.0, text=message)
                
                # İstatistikleri güncelle
                if stats and stats_placeholder:
                    stats_placeholder.metric(
                        label="Güncelleme Hızı",
                        value=f"{stats.get('rate', 0):.1f} varyant/saniye",
                        delta=f"Tahmini süre: {stats.get('eta', 0):.1f} dakika"
                    )
                
                if log_detail and log_placeholder:
                    st.session_state.sync_log_list.insert(0, log_detail)
                    log_html = "".join(st.session_state.sync_log_list[:50])
                    log_placeholder.markdown(
                        f'<div style="height:200px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{log_html}</div>', 
                        unsafe_allow_html=True
                    )
            
            try:
                shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                
                # Hangi fiyatları güncelleyeceğimizi belirle
                calculated_data_df, price_col, compare_col = pd.DataFrame(), None, None
                if update_choice == "Ana Fiyatlar":
                    calculated_data_df = df
                    price_col = 'NIHAI_SATIS_FIYATI'
                    compare_col = None
                else: 
                    calculated_data_df = st.session_state.retail_df
                    price_col = 'İNDİRİMLİ SATIŞ FİYATI'
                    compare_col = 'NIHAI_SATIS_FIYATI'
                
                # Devam et modunda sadece başarısız olanları güncelle
                variants_to_update = st.session_state.df_variants
                if continue_from_last and 'last_failed_skus' in st.session_state:
                    failed_skus = st.session_state.last_failed_skus
                    if failed_skus:
                        st.info(f"🔄 {len(failed_skus)} başarısız varyant tekrar denenecek...")
                        variants_to_update = variants_to_update[variants_to_update['MODEL KODU'].isin(failed_skus)]
                
                # Batch işleme
                total_variants = len(variants_to_update)
                all_results = {"success": 0, "failed": 0, "errors": [], "details": []}
                
                for batch_start in range(0, total_variants, batch_size):
                    batch_end = min(batch_start + batch_size, total_variants)
                    batch_variants = variants_to_update.iloc[batch_start:batch_end]
                    
                    st.info(f"📦 Batch {batch_start//batch_size + 1}: {batch_start+1}-{batch_end} arası varyantlar işleniyor...")
                    
                    results = send_prices_to_shopify(
                        shopify_api=shopify_api,
                        calculated_df=calculated_data_df,
                        variants_df=batch_variants,
                        price_column_name=price_col,
                        compare_price_column_name=compare_col,
                        progress_callback=shopify_progress_callback,
                        worker_count=worker_count,
                        max_retries=retry_count
                    )
                    
                    # Sonuçları birleştir
                    all_results["success"] += results.get("success", 0)
                    all_results["failed"] += results.get("failed", 0)
                    all_results["errors"].extend(results.get("errors", []))
                    all_results["details"].extend(results.get("details", []))
                    
                    # Batch arası kısa bekleme (rate limit için)
                    if batch_end < total_variants:
                        time.sleep(2)
                
                # Sonuçları session state'e kaydet (devam et özelliği için)
                st.session_state.last_update_results = all_results
                
                # Başarısız SKU'ları kaydet
                failed_details = [d for d in all_results["details"] if d["status"] == "failed"]
                st.session_state.last_failed_skus = [d["sku"] for d in failed_details]
                
                progress_bar.empty()
                log_placeholder.empty()
                stats_placeholder.empty()

                # Sonuç özeti
                if all_results.get('success', 0) > 0:
                    st.success(f"İşlem Tamamlandı! ✅ {all_results.get('success', 0)} varyant başarıyla güncellendi.")
                
                if all_results.get('failed', 0) > 0:
                    st.error(f"❌ {all_results.get('failed', 0)} varyant güncellenirken hata oluştu.")
                    if st.button("🔄 Başarısız olanları tekrar dene", use_container_width=True):
                        st.rerun()
                
                # Detaylı rapor
                if all_results.get('details'):
                    st.markdown("---")
                    st.markdown("### 📊 Güncelleme Raporu")
                    
                    report_df = pd.DataFrame(all_results['details'])
                    
                    # Özet metrikleri göster
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Toplam İşlenen", len(report_df))
                    with col2:
                        st.metric("Başarılı", len(report_df[report_df['status'] == 'success']))
                    with col3:
                        st.metric("Başarısız", len(report_df[report_df['status'] == 'failed']))
                    with col4:
                        success_rate = (len(report_df[report_df['status'] == 'success']) / len(report_df) * 100) if len(report_df) > 0 else 0
                        st.metric("Başarı Oranı", f"{success_rate:.1f}%")
                    
                    # Detaylı tablolar
                    tab1, tab2 = st.tabs(["✅ Başarılı Güncellenenler", "❌ Başarısız Olanlar"])
                    
                    with tab1:
                        success_df = report_df[report_df['status'] == 'success']
                        if not success_df.empty:
                            st.dataframe(
                                success_df[['sku', 'price']].head(100),
                                use_container_width=True,
                                hide_index=True
                            )
                            if len(success_df) > 100:
                                st.info(f"İlk 100 kayıt gösteriliyor. Toplam: {len(success_df)}")
                        else:
                            st.info("Hiçbir varyant başarıyla güncellenemedi.")
                    
                    with tab2:
                        failed_df = report_df[report_df['status'] == 'failed']
                        if not failed_df.empty:
                            st.dataframe(
                                failed_df[['sku', 'price', 'reason']],
                                use_container_width=True,
                                hide_index=True
                            )
                            
                            # Hata analizi
                            st.markdown("#### 🔍 Hata Analizi")
                            error_counts = failed_df['reason'].value_counts().head(10)
                            for error, count in error_counts.items():
                                st.text(f"• {error[:100]}... ({count} kez)")
                        else:
                            st.info("Tüm varyantlar başarıyla güncellendi!")
                            
            except Exception as e:
                st.error("Güncelleme sırasında beklenmedik bir hata oluştu:")
                st.exception(e)
            finally:
                if 'progress_bar' in locals():
                    progress_bar.empty()
                if 'stats_placeholder' in locals():
                    stats_placeholder.empty()