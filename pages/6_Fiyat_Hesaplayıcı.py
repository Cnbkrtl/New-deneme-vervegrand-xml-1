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
import logging

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
            
            # Session state'e güncelleme durumunu kaydet
            st.session_state.update_in_progress = True
            st.session_state.sync_log_list = []
            
            # Ana konteynerler
            status_container = st.container()
            progress_container = st.container()
            log_container = st.container()
            
            with progress_container:
                progress_bar = st.progress(0, text="Güncelleme işlemi başlatılıyor...")
                col1, col2, col3 = st.columns(3)
                with col1:
                    speed_metric = st.empty()
                with col2:
                    eta_metric = st.empty()
                with col3:
                    status_metric = st.empty()
            
            with log_container:
                log_placeholder = st.empty()
            
            def shopify_progress_callback(data):
                progress = data.get('progress', 0)
                message = data.get('message', 'İşleniyor...')
                log_detail = data.get('log_detail')
                stats = data.get('stats')
                
                # Progress bar güncelle
                progress_bar.progress(progress / 100.0, text=message)
                
                # İstatistikleri güncelle
                if stats:
                    speed_metric.metric("Hız", f"{stats.get('rate', 0):.1f} varyant/sn")
                    eta_metric.metric("Tahmini Süre", f"{stats.get('eta', 0):.1f} dakika")
                    status_metric.metric("İşlem", f"%{progress}")
                
                # Log güncelle
                if log_detail:
                    st.session_state.sync_log_list.insert(0, f"<div>{log_detail}</div>")
                    # Son 30 logu göster
                    log_html = "".join(st.session_state.sync_log_list[:30])
                    log_placeholder.markdown(
                        f'''<div style="
                            height:150px;
                            overflow-y:auto;
                            border:1px solid #444;
                            background:#1e1e1e;
                            padding:10px;
                            border-radius:5px;
                            font-family:monospace;
                            font-size:12px;
                            color:#00ff00;">
                            {log_html}
                        </div>''', 
                        unsafe_allow_html=True
                    )
            
            try:
                shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                
                # Hangi fiyatları güncelleyeceğimizi belirle
                if update_choice == "Ana Fiyatlar":
                    calculated_data_df = st.session_state.calculated_df
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
                        with status_container:
                            st.info(f"🔄 {len(failed_skus)} başarısız varyant tekrar denenecek...")
                        variants_to_update = variants_to_update[variants_to_update['MODEL KODU'].isin(failed_skus)]
                
                # Batch işleme - İyileştirilmiş
                total_variants = len(variants_to_update)
                all_results = {"success": 0, "failed": 0, "errors": [], "details": []}
                
                # Dinamik batch boyutu
                actual_batch_size = min(batch_size, 1000) if total_variants > 5000 else batch_size
                actual_worker_count = min(worker_count, 7) if total_variants > 5000 else worker_count
                
                total_batches = (total_variants + actual_batch_size - 1) // actual_batch_size
                
                # Batch durumu için container
                batch_status_container = st.container()
                
                for batch_num, batch_start in enumerate(range(0, total_variants, actual_batch_size), 1):
                    batch_end = min(batch_start + actual_batch_size, total_variants)
                    batch_variants = variants_to_update.iloc[batch_start:batch_end]
                    
                    # Batch bilgisi
                    with batch_status_container:
                        batch_col1, batch_col2, batch_col3 = st.columns(3)
                        with batch_col1:
                            st.info(f"📦 Batch {batch_num}/{total_batches}")
                        with batch_col2:
                            st.info(f"📊 Varyant {batch_start+1}-{batch_end}")
                        with batch_col3:
                            batch_progress = st.progress(0)
                    
                    # Batch progress callback wrapper
                    def batch_progress_callback(data):
                        # Batch içi progress
                        if 'progress' in data:
                            batch_internal_progress = data['progress'] / 100
                            batch_progress.progress(batch_internal_progress)
                        
                        # Ana progress callback'i çağır
                        shopify_progress_callback(data)
                    
                    try:
                        # Batch işleme
                        batch_start_time = time.time()
                        
                        results = send_prices_to_shopify(
                            shopify_api=shopify_api,
                            calculated_df=calculated_data_df,
                            variants_df=batch_variants,
                            price_column_name=price_col,
                            compare_price_column_name=compare_col,
                            progress_callback=batch_progress_callback,
                            worker_count=actual_worker_count,
                            max_retries=retry_count
                        )
                        
                        batch_elapsed = time.time() - batch_start_time
                        
                        # Sonuçları birleştir
                        all_results["success"] += results.get("success", 0)
                        all_results["failed"] += results.get("failed", 0)
                        all_results["errors"].extend(results.get("errors", []))
                        all_results["details"].extend(results.get("details", []))
                        
                        # Batch özeti
                        with batch_status_container:
                            if results.get('success', 0) > 0:
                                st.success(f"✅ Batch {batch_num}: {results.get('success', 0)} başarılı, {results.get('failed', 0)} başarısız ({batch_elapsed:.1f}s)")
                            elif results.get('failed', 0) > 0:
                                st.warning(f"⚠️ Batch {batch_num}: Tümü başarısız ({results.get('failed', 0)} varyant)")
                        
                        # Session state'i güncelle (kesinti durumunda kurtarma için)
                        st.session_state.last_batch_completed = batch_num
                        st.session_state.interim_results = all_results
                        
                    except Exception as batch_error:
                        st.error(f"Batch {batch_num} hatası: {str(batch_error)[:200]}")
                        logging.error(f"Batch {batch_num} hatası: {batch_error}")
                        
                        # Hata durumunda da devam et
                        all_results["errors"].append(f"Batch {batch_num}: {str(batch_error)[:100]}")
                    
                    # Batch arası işlemler
                    if batch_num < total_batches:
                        # Session'ı canlı tut
                        if batch_num % 3 == 0:
                            st.empty()  # UI yenileme
                            time.sleep(0.5)
                        
                        # Rate limit için bekleme
                        wait_time = 2 if total_variants > 5000 else 1
                        time.sleep(wait_time)
                        
                        # İlerleme durumunu göster
                        overall_progress = int((batch_num / total_batches) * 100)
                        progress_bar.progress(overall_progress / 100, text=f"Genel ilerleme: {overall_progress}%")
                
                # Sonuçları kaydet
                st.session_state.last_update_results = all_results
                st.session_state.update_in_progress = False
                
                # Başarısız SKU'ları kaydet
                failed_details = [d for d in all_results["details"] if d.get("status") == "failed"]
                st.session_state.last_failed_skus = [d.get("sku") for d in failed_details if d.get("sku")]
                
                # Temizlik
                progress_bar.empty()
                batch_progress.empty()
                
                # Final sonuç özeti
                st.markdown("---")
                st.markdown("## 📊 Güncelleme Özeti")
                
                summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
                with summary_col1:
                    st.metric("Toplam İşlenen", total_variants)
                with summary_col2:
                    st.metric("✅ Başarılı", all_results.get('success', 0))
                with summary_col3:
                    st.metric("❌ Başarısız", all_results.get('failed', 0))
                with summary_col4:
                    success_rate = (all_results.get('success', 0) / total_variants * 100) if total_variants > 0 else 0
                    st.metric("Başarı Oranı", f"{success_rate:.1f}%")
                
                # Başarısız olanları tekrar deneme seçeneği
                if all_results.get('failed', 0) > 0:
                    st.error(f"❌ {all_results.get('failed', 0)} varyant güncellenemedi.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔄 Başarısız Olanları Tekrar Dene", use_container_width=True):
                            st.session_state.continue_from_last = True
                            st.rerun()
                    with col2:
                        # Başarısız SKU'ları indir
                        if failed_details:
                            failed_df = pd.DataFrame(failed_details)
                            csv = failed_df.to_csv(index=False)
                            st.download_button(
                                label="📥 Başarısız SKU'ları İndir",
                                data=csv,
                                file_name=f"basarisiz_skular_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                else:
                    st.success(f"🎉 Tüm {all_results.get('success', 0)} varyant başarıyla güncellendi!")
                
                # Detaylı rapor (isteğe bağlı)
                with st.expander("📋 Detaylı Rapor", expanded=False):
                    if all_results.get('details'):
                        report_df = pd.DataFrame(all_results['details'])
                        
                        tab1, tab2 = st.tabs(["✅ Başarılı", "❌ Başarısız"])
                        
                        with tab1:
                            success_df = report_df[report_df['status'] == 'success']
                            if not success_df.empty:
                                st.dataframe(
                                    success_df[['sku', 'price']].head(200),
                                    use_container_width=True,
                                    hide_index=True
                                )
                        
                        with tab2:
                            failed_df = report_df[report_df['status'] == 'failed']
                            if not failed_df.empty:
                                # Hata gruplandırması
                                st.markdown("#### Hata Dağılımı")
                                error_summary = failed_df['reason'].value_counts().head(10)
                                st.bar_chart(error_summary)
                                
                                st.markdown("#### Başarısız Varyantlar")
                                st.dataframe(
                                    failed_df[['sku', 'price', 'reason']].head(200),
                                    use_container_width=True,
                                    hide_index=True
                                )
                
            except Exception as e:
                st.error("Güncelleme sırasında kritik hata:")
                st.exception(e)
                st.session_state.update_in_progress = False
            
            finally:
                # Temizlik
                if 'progress_bar' in locals():
                    progress_bar.empty()
                if 'batch_progress' in locals():
                    batch_progress.empty()