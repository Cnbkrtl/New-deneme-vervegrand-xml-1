# 3_sync.py

import streamlit as st
import threading
import queue
import time
import pandas as pd
from shopify_sync import sync_products_from_sentos_api, sync_missing_products_only, sync_single_product_by_sku
from log_manager import save_log
from datetime import timedelta

# --- Session State Başlatma ---
# Ana senkronizasyon için durumlar
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
if 'stop_sync_event' not in st.session_state:
    st.session_state.stop_sync_event = None
if 'progress_queue' not in st.session_state:
    st.session_state.progress_queue = queue.Queue()
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = None
if 'live_log' not in st.session_state:
    st.session_state.live_log = []

# "Eksik Ürünleri Oluştur" özelliği için ayrı durumlar
if 'sync_missing_running' not in st.session_state:
    st.session_state.sync_missing_running = False
if 'sync_missing_results' not in st.session_state:
    st.session_state.sync_missing_results = None
if 'live_log_missing' not in st.session_state:
    st.session_state.live_log_missing = []
if 'start_time_missing' not in st.session_state:
    st.session_state.start_time_missing = 0


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

# --- ARAYÜZ MANTIĞI ---
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected')

# Herhangi bir senkronizasyonun çalışıp çalışmadığını kontrol eden yardımcı değişken
is_any_sync_running = st.session_state.sync_running or st.session_state.sync_missing_running

if not sync_ready:
    st.warning("⚠️ Lütfen senkronizasyonu başlatmadan önce Ayarlar sayfasında her iki API bağlantısını da yapılandırın.")
else:
    # --- BÖLÜM 1: ANA SENKRONİZASYON KONTROL PANELİ (DEĞİŞİKLİK YOK) ---
    st.subheader("Yeni Bir Senkronizasyon Görevi Başlat")
    
    sync_mode = st.selectbox(
        "Senkronizasyon Tipi Seçin",
        [
            "Full Sync (Create & Update All)", "Stock & Variants Only", "Images Only",
            "Images with SEO Alt Text", "Descriptions Only", "Categories (Product Type) Only",
        ],
        index=0, help="Gerçekleştirmek istediğiniz senkronizasyon görevini seçin."
    )

    col_opts1, col_opts2 = st.columns(2)
    with col_opts1:
        test_mode = st.checkbox("Test Modu (İlk 20 ürünü senkronize et)", value=True, help="Tam bir senkronizasyon çalıştırmadan bağlantıyı ve mantığı test etmek için yalnızca Sentos'tan ilk 20 ürünü işler.")
    with col_opts2:
        max_workers = st.number_input(
            "Eşzamanlı İşlem Sayısı", min_value=1, max_value=50, value=5, 
            help="Paralel olarak işlenecek ürün sayısı. API hız sınırlarını aşmamak için dikkatli artırın."
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Senkronizasyonu Başlat", type="primary", use_container_width=True, disabled=is_any_sync_running):
            if all(st.session_state.get(key) for key in ['shopify_store', 'shopify_token', 'sentos_api_url', 'sentos_api_key', 'sentos_api_secret']):
                st.session_state.sync_running = True
                st.session_state.stop_sync_event = threading.Event()
                st.session_state.sync_results = None
                st.session_state.live_log = []
                st.session_state.start_time = time.monotonic()
                st.session_state.selected_sync_mode = sync_mode
                
                thread = threading.Thread(
                    target=sync_products_from_sentos_api,
                    args=(
                        st.session_state.shopify_store, st.session_state.shopify_token,
                        st.session_state.sentos_api_url, st.session_state.sentos_api_key,
                        st.session_state.sentos_api_secret, st.session_state.sentos_cookie,
                        test_mode, lambda update: st.session_state.progress_queue.put(update),
                        st.session_state.stop_sync_event, max_workers, sync_mode
                    ), daemon=True
                )
                st.session_state.sync_thread = thread
                thread.start()
                st.rerun()
            else:
                st.error("❌ Senkronizasyon başlatılamıyor. Lütfen Ayarlar sayfasında tüm API ayarlarının kaydedildiğinden emin olun.")

    with col2:
        if st.button("🛑 Senkronizasyonu Durdur", use_container_width=True, disabled=not is_any_sync_running):
            if st.session_state.stop_sync_event:
                st.session_state.stop_sync_event.set()
                st.warning("Durdurma sinyali gönderildi. Mevcut işlemlerin bitmesi bekleniyor...")
    
    st.markdown("---")

    # --- Ana senkronizasyon için ilerleme takibi (DEĞİŞİKLİK YOK) ---
    if st.session_state.sync_running:
        st.subheader("📊 Ana Senkronizasyon Devam Ediyor...")
        progress_bar = st.progress(0, text="Başlatılıyor...")
        stats_placeholder = st.empty()
        log_expander = st.expander("Canlı Ürün Loglarını Göster", expanded=True)
        with log_expander:
            log_placeholder = st.empty()
        
        progress_percentage = 0 
        while 'sync_thread' in st.session_state and st.session_state.sync_thread is not None and st.session_state.sync_thread.is_alive():
            try:
                update = st.session_state.progress_queue.get(timeout=1)
                
                if update.get('status') == 'done':
                    st.session_state.sync_results = update.get('results')
                    st.session_state.sync_running = False
                    break
                elif update.get('status') == 'error':
                    st.error(f"Bir hata oluştu: {update.get('message')}")
                    st.session_state.sync_results = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                    st.session_state.sync_running = False
                    break
                
                if 'progress' in update: progress_percentage = max(0, min(100, update['progress']))
                if 'message' in update: progress_bar.progress(progress_percentage / 100.0, text=update['message'])

                if 'stats' in update:
                    stats = update['stats']
                    with stats_placeholder.container():
                        st.metric("İşlenen Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
                        kpi_cols = st.columns(4)
                        kpi_cols[0].metric("✅ Oluşturulan", stats.get('created', 0))
                        kpi_cols[1].metric("🔄 Güncellenen", stats.get('updated', 0))
                        kpi_cols[2].metric("❌ Hatalı", stats.get('failed', 0), delta_color="inverse")
                        kpi_cols[3].metric("⏭️ Atlanan", stats.get('skipped', 0))
                
                if 'log_detail' in update:
                    st.session_state.live_log.insert(0, update['log_detail'])
                    with log_placeholder.container():
                        log_html = "".join(st.session_state.live_log[:50])
                        st.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{log_html}</div>', unsafe_allow_html=True)
            except queue.Empty: pass
        
        if not st.session_state.sync_running:
            st.rerun()

    if st.session_state.sync_results:
        st.subheader("✅ Ana Senkronizasyon Görevi Tamamlandı")
        results = st.session_state.sync_results
        stats = results.get('stats', {})
        
        if results and stats:
            duration_str = results.get('duration', 'N/A')
            results['sync_mode'] = st.session_state.get('selected_sync_mode', 'Bilinmiyor')
            save_log(results)
            st.success(f"Senkronizasyon görevi {duration_str} içinde tamamlandı. Özet aşağıdadır.")
        
        st.metric("İşlenen Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
        kpi_cols = st.columns(4)
        kpi_cols[0].metric("✅ Oluşturulan", stats.get('created', 0))
        kpi_cols[1].metric("🔄 Güncellenen", stats.get('updated', 0))
        kpi_cols[2].metric("❌ Hatalı", stats.get('failed', 0), delta_color="inverse")
        kpi_cols[3].metric("⏭️ Atlanan", stats.get('skipped', 0))
        
        with st.expander("Detaylı Raporu Görüntüle", expanded=False):
            if details := results.get('details', []):
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                st.info("Bu çalışma için detaylı ürün logu oluşturulmadı.")


    # --- YENİ BÖLÜM 2: SADECE EKSİK ÜRÜNLERİ OLUŞTUR ---
    st.markdown("---")
    with st.expander("✨ **Yeni Özellik: Sadece Eksik Ürünleri Oluştur**"):
        st.info("Bu araç, Sentos'taki ürün listesini Shopify ile karşılaştırır ve sadece Shopify'da olmayan ürünleri oluşturur. Mevcut ürünlere dokunmaz.")
        
        missing_test_mode = st.checkbox("Test Modu (İlk 20 ürünü tara)", value=True, key="missing_test_mode")
        
        if st.button("🚀 Eksik Ürünleri Bul ve Oluştur", use_container_width=True, disabled=is_any_sync_running):
            st.session_state.sync_missing_running = True
            st.session_state.stop_sync_event = threading.Event()
            st.session_state.sync_missing_results = None
            st.session_state.live_log_missing = []
            st.session_state.start_time_missing = time.monotonic()
            
            thread = threading.Thread(
                target=sync_missing_products_only,
                args=(
                    st.session_state.shopify_store, st.session_state.shopify_token,
                    st.session_state.sentos_api_url, st.session_state.sentos_api_key,
                    st.session_state.sentos_api_secret, st.session_state.sentos_cookie,
                    missing_test_mode, lambda update: st.session_state.progress_queue.put(update),
                    st.session_state.stop_sync_event, max_workers
                ), daemon=True
            )
            st.session_state.sync_thread = thread
            thread.start()
            st.rerun()

    # --- Eksik ürün senkronizasyonu için ilerleme takibi ---
    if st.session_state.sync_missing_running:
        st.subheader("📊 Eksik Ürünler Oluşturuluyor...")
        progress_bar_missing = st.progress(0, text="Başlatılıyor...")
        stats_placeholder_missing = st.empty()
        log_expander_missing = st.expander("Canlı Ürün Oluşturma Logları", expanded=True)
        with log_expander_missing:
            log_placeholder_missing = st.empty()
        
        progress_percentage = 0
        while 'sync_thread' in st.session_state and st.session_state.sync_thread is not None and st.session_state.sync_thread.is_alive():
            try:
                update = st.session_state.progress_queue.get(timeout=1)
                
                if update.get('status') == 'done':
                    st.session_state.sync_missing_results = update.get('results')
                    st.session_state.sync_missing_running = False
                    break
                elif update.get('status') == 'error':
                    st.error(f"Bir hata oluştu: {update.get('message')}")
                    st.session_state.sync_missing_results = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                    st.session_state.sync_missing_running = False
                    break
                
                if 'progress' in update: progress_percentage = max(0, min(100, update['progress']))
                if 'message' in update: progress_bar_missing.progress(progress_percentage / 100.0, text=update['message'])

                if 'stats' in update:
                    stats = update['stats']
                    with stats_placeholder_missing.container():
                        st.metric("Oluşturulacak Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
                        kpi_cols = st.columns(2)
                        kpi_cols[0].metric("✅ Oluşturulan", stats.get('created', 0))
                        kpi_cols[1].metric("❌ Hatalı", stats.get('failed', 0), delta_color="inverse")

                if 'log_detail' in update:
                    st.session_state.live_log_missing.insert(0, update['log_detail'])
                    with log_placeholder_missing.container():
                        log_html = "".join(st.session_state.live_log_missing[:50])
                        st.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;">{log_html}</div>', unsafe_allow_html=True)

            except queue.Empty: pass
        
        if not st.session_state.sync_missing_running:
            st.rerun()

    if st.session_state.sync_missing_results:
        st.subheader("✅ Eksik Ürün Oluşturma Görevi Tamamlandı")
        results = st.session_state.sync_missing_results
        stats = results.get('stats', {})
        duration_str = results.get('duration', 'N/A')
        
        results['sync_mode'] = 'Create Missing Only'
        save_log(results)
        st.success(f"Görev {duration_str} içinde tamamlandı. Özet aşağıdadır.")
        
        st.metric("İşlenen Toplam Ürün", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
        kpi_cols = st.columns(2)
        kpi_cols[0].metric("✅ Oluşturulan", stats.get('created', 0))
        kpi_cols[1].metric("❌ Hatalı", stats.get('failed', 0), delta_color="inverse")
        
        with st.expander("Detaylı Raporu Görüntüle", expanded=False):
            if details := results.get('details', []):
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                st.info("Bu çalışma için detaylı ürün logu oluşturulmadı.")


    # --- YENİ BÖLÜM 3: TEKİL ÜRÜN GÜNCELLEME (SKU İLE) ---
    st.markdown("---")
    with st.expander("✨ **Yeni Özellik: SKU ile Tekil Ürün Güncelle**"):
        st.info("Sentos'ta bulunan bir ürünün model kodunu (SKU) buraya yazarak, Shopify'daki karşılığını anında tam olarak güncelleyebilirsiniz.")
        
        sku_to_sync = st.text_input("Model Kodu (SKU)", placeholder="Örn: V-123-ABC")
        
        if st.button("🔄 Ürünü Bul ve Senkronize Et", use_container_width=True, disabled=is_any_sync_running):
            if not sku_to_sync:
                st.warning("Lütfen bir SKU girin.")
            else:
                with st.spinner(f"'{sku_to_sync}' SKU'lu ürün aranıyor ve senkronize ediliyor..."):
                    result = sync_single_product_by_sku(
                        st.session_state.shopify_store, st.session_state.shopify_token,
                        st.session_state.sentos_api_url, st.session_state.sentos_api_key,
                        st.session_state.sentos_api_secret, st.session_state.sentos_cookie,
                        sku_to_sync
                    )
                if result.get('success'):
                    st.success(f"✅ Başarılı: {result.get('message')}")
                else:
                    st.error(f"❌ Hata: {result.get('message')}")