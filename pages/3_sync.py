# 3_sync.py

import streamlit as st
import threading
import queue
import time
import pandas as pd
from shopify_sync import sync_products_from_sentos_api
from log_manager import save_log
from datetime import timedelta

# --- Session State Başlatma ---
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

# --- Giriş Kontrolü ---
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- Sayfa Başlığı ---
st.markdown("""
<div class="main-header">
    <h1>🚀 Sync Products</h1>
    <p>Start, monitor, and review synchronization tasks between Sentos and Shopify.</p>
</div>
""", unsafe_allow_html=True)

# --- ARAYÜZ MANTIĞI ---
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected')

if not sync_ready:
    st.warning("⚠️ Please configure and test both API connections in Settings before starting a sync.")
else:
    # --- Senkronizasyon Kontrol Paneli ---
    st.subheader("Start a New Sync Task")
    
    sync_mode = st.selectbox(
        "Select Sync Type",
        [
            "Full Sync (Create & Update All)",
            "Stock & Variants Only",
            "Images Only",
            "Images with SEO Alt Text",
            "Descriptions Only",
            "Categories (Product Type) Only",
        ],
        index=0,
        help="Choose the specific synchronization task you want to perform."
    )

    col_opts1, col_opts2 = st.columns(2)
    with col_opts1:
        test_mode = st.checkbox("Test Mode (Sync first 20 products)", value=True, help="Only processes the first 20 products from Sentos to test the connection and logic without running a full sync.")
    with col_opts2:
        max_workers = st.number_input(
            "Concurrent Workers", 
            min_value=1, 
            max_value=10, 
            value=3, 
            help="Number of products to process in parallel. Increase carefully to avoid API rate limits."
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Start Sync", type="primary", use_container_width=True, disabled=st.session_state.sync_running):
            if all(st.session_state.get(key) for key in ['shopify_store', 'shopify_token', 'sentos_api_url', 'sentos_api_key', 'sentos_api_secret', 'sentos_cookie']):
                st.session_state.sync_running = True
                st.session_state.stop_sync_event = threading.Event()
                st.session_state.sync_results = None
                st.session_state.live_log = []
                st.session_state.start_time = time.monotonic()
                st.session_state.selected_sync_mode = sync_mode
                
                progress_q = st.session_state.progress_queue

                thread = threading.Thread(
                    target=sync_products_from_sentos_api,
                    args=(
                        st.session_state.shopify_store, st.session_state.shopify_token,
                        st.session_state.sentos_api_url, st.session_state.sentos_api_key,
                        st.session_state.sentos_api_secret, st.session_state.sentos_cookie,
                        test_mode,
                        lambda update: progress_q.put(update),
                        st.session_state.stop_sync_event,
                        max_workers,
                        sync_mode
                    ),
                    daemon=True
                )
                st.session_state.sync_thread = thread
                thread.start()
                st.rerun()
            else:
                st.error("❌ Cannot start sync. Please ensure all API settings and the cookie are saved on the Settings page.")

    with col2:
        if st.button("🛑 Stop Sync", use_container_width=True, disabled=not st.session_state.sync_running):
            if st.session_state.stop_sync_event:
                st.session_state.stop_sync_event.set()
                st.warning("Stop signal sent. Waiting for the current product to finish...")
    
    st.markdown("---")

    if st.session_state.sync_running:
        st.subheader("📊 Sync in Progress...")
        progress_bar = st.progress(0, text="Starting...")
        stats_placeholder = st.empty()
        
        # <--- GÜNCELLEME: Canlı log alanı için de bir yer tutucu (placeholder) oluşturuyoruz ---
        log_expander = st.expander("Show Live Product Log", expanded=True)
        with log_expander:
            log_placeholder = st.empty()
        
        progress_percentage = 0 
        
        while 'sync_thread' in st.session_state and st.session_state.sync_thread.is_alive():
            try:
                update = st.session_state.progress_queue.get(timeout=1)
                
                if update.get('status') == 'done':
                    st.session_state.sync_results = update.get('results')
                    st.session_state.sync_running = False
                    break
                elif update.get('status') == 'error':
                    st.error(f"An error occurred: {update.get('message')}")
                    st.session_state.sync_results = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                    st.session_state.sync_running = False
                    break
                
                if 'progress' in update:
                    progress_percentage = max(0, min(100, update['progress']))
                
                if 'message' in update:
                    progress_bar.progress(progress_percentage / 100.0, text=update['message'])

                if 'stats' in update:
                    stats = update['stats']
                    with stats_placeholder.container():
                        st.metric("Total Products to Process", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
                        kpi_cols = st.columns(4)
                        kpi_cols[0].metric("✅ Created", stats.get('created', 0))
                        kpi_cols[1].metric("🔄 Updated", stats.get('updated', 0))
                        kpi_cols[2].metric("❌ Failed", stats.get('failed', 0), delta_color="inverse")
                        kpi_cols[3].metric("⏭️ Skipped", stats.get('skipped', 0))
                
                # <--- GÜNCELLEME: Logları st.empty() yer tutucusunun içinde yeniden çiziyoruz ---
                if 'log_detail' in update:
                    st.session_state.live_log.insert(0, update['log_detail'])
                    with log_placeholder.container():
                        # Gelen log_detail'ler zaten HTML formatında olduğu için doğrudan birleştiriyoruz
                        log_html = "".join(st.session_state.live_log[:50])
                        st.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{log_html}</div>', unsafe_allow_html=True)

            except queue.Empty:
                pass
            except Exception as e:
                st.error(f"An unexpected error occurred in the UI update loop: {e}")
                st.session_state.sync_running = False
                break
        
        if not st.session_state.sync_running:
            st.rerun()

    if st.session_state.sync_results:
        st.subheader("✅ Sync Task Completed")
        results = st.session_state.sync_results
        stats = results.get('stats', {})
        
        if results and stats:
            end_time = time.monotonic()
            start_time = st.session_state.get('start_time', end_time)
            duration_seconds = end_time - start_time
            
            results['sync_mode'] = st.session_state.get('selected_sync_mode', 'Full Sync')
            results['duration'] = str(timedelta(seconds=duration_seconds)).split('.')[0]
            save_log(results)

        duration_str = results.get('duration', 'N/A')
        st.success(f"The synchronization task finished in {duration_str}. See the summary below.")
        
        st.metric("Total Products Processed", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")

        kpi_cols = st.columns(4)
        kpi_cols[0].metric("✅ Created", stats.get('created', 0))
        kpi_cols[1].metric("🔄 Updated", stats.get('updated', 0))
        kpi_cols[2].metric("❌ Failed", stats.get('failed', 0), delta_color="inverse")
        kpi_cols[3].metric("⏭️ Skipped", stats.get('skipped', 0))
        
        with st.expander("View Detailed Log", expanded=False):
            details = results.get('details', [])
            if details:
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                st.info("No detailed product logs were generated for this run.")