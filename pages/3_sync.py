# 3_sync.py

import streamlit as st
import time
import pandas as pd
import threading
import queue
from log_manager import save_log
from shopify_sync import sync_products_from_sentos_api

# --- Session State Başlatma ---
# Bu değerler sayfa yenilense bile korunur
if 'sync_thread' not in st.session_state:
    st.session_state.sync_thread = None
if 'stop_event' not in st.session_state:
    st.session_state.stop_event = None
if 'progress_queue' not in st.session_state:
    st.session_state.progress_queue = None
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = None
if 'live_log_details' not in st.session_state:
    st.session_state.live_log_details = []


# --- Giriş Kontrolü ---
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

# --- Sayfa Başlığı ---
st.markdown("""
<div class="main-header">
    <h1>🚀 Ürünleri Senkronize Et</h1>
    <p>Sentos ve Shopify arasındaki senkronizasyon görevlerini başlatın, izleyin ve inceleyin.</p>
</div>
""", unsafe_allow_html=True)


# --- Arayüz Mantığı ---
# API bağlantıları ayarlar sayfasında test edilmiş olmalı
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected')

if not sync_ready and not st.session_state.sync_running:
    st.warning("⚠️ Senkronizasyonu başlatmadan önce lütfen Ayarlar sayfasında her iki API bağlantısını da yapılandırın ve test edin.")

# --- Yeni Görev Başlatma Formu ---
if not st.session_state.sync_running:
    st.subheader("Yeni Bir Senkronizasyon Görevi Başlat")
    
    with st.form("new_sync_form"):
        sync_mode = st.selectbox(
            "Senkronizasyon Tipi Seçin", 
            [
                "Full Sync (Create & Update All)", 
                "Stock & Variants Only", 
                "Images Only", 
                "Images with SEO Alt Text", 
                "Descriptions Only", 
                "Categories (Product Type) Only"
            ]
        )
        test_mode = st.checkbox("Test Modu (Sadece ilk 20 ürünü senkronize et)", value=True)
        max_workers = st.number_input("Eşzamanlı İşlem Sayısı (Worker)", min_value=1, max_value=10, value=3)

        submitted = st.form_submit_button("🚀 Senkronizasyonu Başlat", type="primary", use_container_width=True, disabled=not sync_ready)

        if submitted:
            # Yeni bir sync başlatmak için state'leri hazırla
            st.session_state.sync_running = True
            st.session_state.sync_results = None
            st.session_state.live_log_details = []
            st.session_state.stop_event = threading.Event()
            st.session_state.progress_queue = queue.Queue()

            # Callback fonksiyonu: Thread'den gelen veriyi kuyruğa atar
            def progress_callback(data):
                st.session_state.progress_queue.put(data)

            # Arka plan thread'ine verilecek argümanları bir sözlük (kwargs) olarak hazırla
            # Bu yöntem, parametre sırası hatalarını tamamen engeller.
            thread_kwargs = {
                'store_url': st.session_state.shopify_store,
                'access_token': st.session_state.shopify_token,
                'sentos_api_url': st.session_state.sentos_api_url,
                'sentos_api_key': st.session_state.sentos_api_key,
                'sentos_api_secret': st.session_state.sentos_api_secret,
                'sentos_cookie': st.session_state.sentos_cookie,
                'test_mode': test_mode,
                'progress_callback': progress_callback,
                'stop_event': st.session_state.stop_event,
                'max_workers': max_workers,
                'sync_mode': sync_mode
            }

            # Thread'i oluştur ve başlat
            st.session_state.sync_thread = threading.Thread(
                target=sync_products_from_sentos_api, 
                kwargs=thread_kwargs, # Argümanları kwargs olarak ver
                daemon=True
            )
            st.session_state.sync_thread.start()
            st.rerun()


# --- Görev Takip Ekranı ---
if st.session_state.sync_running:
    st.subheader("📊 Senkronizasyon Devam Ediyor...")
    
    if st.button("🛑 Senkronizasyonu Durdur", use_container_width=True):
        if st.session_state.stop_event:
            st.session_state.stop_event.set()
            st.warning("Durdurma sinyali gönderildi. Mevcut işlemlerin bitmesi bekleniyor...")
    
    st.markdown("---")

    # Arayüz elemanları için yer tutucular
    progress_bar = st.progress(0, text="Başlatılıyor...")
    stats_placeholder = st.empty()
    log_expander = st.expander("Canlı Ürün Loglarını Göster", expanded=True)
    with log_expander:
        log_placeholder = st.empty()

    # Thread bitene kadar veya durdurulana kadar arayüzü güncelle
    while st.session_state.sync_thread and st.session_state.sync_thread.is_alive():
        try:
            # Kuyruktan en son veriyi al
            update = st.session_state.progress_queue.get(timeout=1)
            
            if 'progress' in update:
                progress_bar.progress(update['progress'], text=update.get('message', 'İşleniyor...'))
            
            if 'stats' in update:
                stats = update['stats']
                with stats_placeholder.container():
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
                    col2.metric("✅ Yeni", stats.get('created', 0))
                    col3.metric("🔄 Güncellenen", stats.get('updated', 0))
                    col4.metric("❌ Hatalı", stats.get('failed', 0))
                    col5.metric("⏭️ Atlanan", stats.get('skipped', 0))

            if 'log_detail' in update:
                st.session_state.live_log_details.insert(0, update['log_detail'])
                with log_placeholder.container():
                    st.markdown(
                        f'<div style="height:400px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">'
                        f'{"".join(st.session_state.live_log_details[:50])}</div>', 
                        unsafe_allow_html=True
                    )

            if update.get('status') == 'done':
                st.session_state.sync_results = update.get('results')
                st.success("Senkronizasyon başarıyla tamamlandı!")
                break
                
            if update.get('status') == 'error':
                st.session_state.sync_results = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                st.error(f"Senkronizasyon kritik bir hatayla durdu: {update.get('message')}")
                break

        except queue.Empty:
            # Kuyrukta yeni veri yoksa beklemeye devam et
            time.sleep(1)

    # Thread bittiğinde state'i temizle ve sayfayı yenile
    if not (st.session_state.sync_thread and st.session_state.sync_thread.is_alive()):
        st.session_state.sync_running = False
        st.session_state.sync_thread = None
        # Sonuçları göstermek için sayfayı yenilemeden önce kısa bekleme
        if st.session_state.sync_results:
             time.sleep(3)
        st.rerun()


# --- Tamamlanmış Görev Sonuçları ---
if st.session_state.sync_results:
    st.subheader("✅ Senkronizasyon Görevi Tamamlandı")
    results = st.session_state.sync_results
    stats = results.get('stats', {})
    
    if stats:
        duration = results.get('duration', 'Bilinmiyor')
        st.success(f"Senkronizasyon {duration} içinde tamamlandı. Özet aşağıdadır.")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("İşlenen Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
        col2.metric("✅ Yeni Oluşturulan", stats.get('created', 0))
        col3.metric("🔄 Güncellenen", stats.get('updated', 0))
        col4.metric("❌ Başarısız", stats.get('failed', 0))
        col5.metric("⏭️ Atlanan", stats.get('skipped', 0))
        
        # Logları kaydet
        results['sync_mode'] = st.session_state.get('selected_sync_mode', 'N/A')
        save_log(results)

    with st.expander("Detaylı Raporu Görüntüle", expanded=False):
        details = results.get('details', [])
        if details:
            try:
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            except Exception:
                st.error("Rapor görüntülenirken bir hata oluştu.")
                st.json(details)