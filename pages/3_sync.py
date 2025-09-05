# 3_sync.py

import streamlit as st
import threading
import queue
import time
import pandas as pd
from datetime import timedelta

# Arka plandaki ana senkronizasyon fonksiyonlarını içe aktarıyoruz
from shopify_sync import (
    sync_products_from_sentos_api, 
    sync_missing_products_only, 
    sync_single_product_by_sku
)
from log_manager import save_log

# --- Session State Başlatma ---
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
if 'sync_thread' not in st.session_state:
    st.session_state.sync_thread = None
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = None
if 'live_log' not in st.session_state:
    st.session_state.live_log = []

if 'sync_missing_running' not in st.session_state:
    st.session_state.sync_missing_running = False
if 'missing_sync_thread' not in st.session_state:
    st.session_state.missing_sync_thread = None
if 'sync_missing_results' not in st.session_state:
    st.session_state.sync_missing_results = None
if 'live_log_missing' not in st.session_state:
    st.session_state.live_log_missing = []

if 'stop_sync_event' not in st.session_state:
    st.session_state.stop_sync_event = None
# progress_queue'nun burada başlatıldığından emin oluyoruz
if 'progress_queue' not in st.session_state:
    st.session_state.progress_queue = queue.Queue()

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

# --- Arayüz Mantığı ---
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected')

is_any_sync_running = st.session_state.sync_running or st.session_state.sync_missing_running

# --- Ortak İlerleme ve Sonuç Gösterim Fonksiyonları (Değişiklik yok) ---
def display_progress(title, results_key, log_key):
    st.subheader(title)
    if st.button("🛑 Stop Current Task", use_container_width=True, key=f"stop_{results_key}"):
        if st.session_state.stop_sync_event:
            st.session_state.stop_sync_event.set()
            st.warning("Stop signal sent. Waiting for current operations to finish...")

    progress_bar = st.progress(0, text="Starting...")
    stats_placeholder = st.empty()
    log_expander = st.expander("Show Live Log", expanded=True)
    with log_expander:
        log_placeholder = st.empty()

    while True:
        try:
            # Kuyruktan mesajları okumaya devam et
            update = st.session_state.progress_queue.get(timeout=1)
            
            if 'progress' in update:
                progress_bar.progress(update['progress'] / 100.0, text=update.get('message', 'Processing...'))
            
            if 'stats' in update:
                stats = update['stats']
                with stats_placeholder.container():
                    cols = st.columns(5)
                    cols[0].metric("Total", f"{stats.get('processed', 0)}/{stats.get('total', 0)}")
                    cols[1].metric("✅ Created", stats.get('created', 0))
                    cols[2].metric("🔄 Updated", stats.get('updated', 0))
                    cols[3].metric("❌ Failed", stats.get('failed', 0))
                    cols[4].metric("⏭️ Skipped", stats.get('skipped', 0))

            if 'log_detail' in update:
                st.session_state[log_key].insert(0, update['log_detail'])
                log_html = "".join(st.session_state[log_key][:50])
                log_placeholder.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{log_html}</div>', unsafe_allow_html=True)
            
            if update.get('status') in ['done', 'error']:
                if update.get('status') == 'done':
                    st.session_state[results_key] = update.get('results')
                else:
                    st.error(f"An error occurred: {update.get('message')}")
                    st.session_state[results_key] = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                break
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            st.error(f"UI update loop error: {e}")
            break
    
    st.session_state.sync_running = False
    st.session_state.sync_missing_running = False
    st.rerun()

def display_results(title, results):
    # Bu fonksiyonda değişiklik yok
    st.subheader(title)
    stats = results.get('stats', {})
    duration = results.get('duration', 'N/A')
    st.success(f"Task finished in {duration}. See the summary below.")
    cols = st.columns(5)
    cols[0].metric("Total Processed", f"{stats.get('processed', 0)}/{stats.get('total', 0)}")
    cols[1].metric("✅ Created", stats.get('created', 0))
    cols[2].metric("🔄 Updated", stats.get('updated', 0))
    cols[3].metric("❌ Failed", stats.get('failed', 0))
    cols[4].metric("⏭️ Skipped", stats.get('skipped', 0))
    with st.expander("View Detailed Log"):
        details = results.get('details', [])
        if details:
            st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
        else:
            st.info("No detailed logs were generated.")

# --- Ana Arayüz Mantığı ---
if not sync_ready and not is_any_sync_running:
    st.warning("⚠️ Please configure and test both API connections in Settings before starting a sync.")

elif st.session_state.sync_running:
    display_progress("📊 Sync in Progress...", 'sync_results', 'live_log')
elif st.session_state.sync_missing_running:
    display_progress("📊 Creating Missing Products...", 'sync_missing_results', 'live_log_missing')

else:
    if st.session_state.sync_results:
        display_results("✅ Sync Task Completed", st.session_state.sync_results)
        st.session_state.sync_results = None
    if st.session_state.sync_missing_results:
        display_results("✅ Missing Products Task Completed", st.session_state.sync_missing_results)
        st.session_state.sync_missing_results = None

    st.markdown("---")
    st.subheader("Start a New General Sync Task")
    
    sync_mode = st.selectbox("Select Sync Type", ["Full Sync (Create & Update All)", "Stock & Variants Only", "Images Only", "Images with SEO Alt Text", "Descriptions Only", "Categories (Product Type) Only"], index=0)
    col1, col2 = st.columns(2)
    test_mode = col1.checkbox("Test Mode (Sync first 20 products)", value=True)
    max_workers = col2.number_input("Concurrent Workers", 1, 50, 5)

    if st.button("🚀 Start General Sync", type="primary", use_container_width=True, disabled=not sync_ready):
        st.session_state.sync_running = True
        st.session_state.live_log = []
        st.session_state.stop_sync_event = threading.Event()
        
        # ### DEĞİŞİKLİK BURADA ###
        # Lambda yerine, kuyruğun .put metodunu doğrudan iletiyoruz.
        thread_kwargs = {
            'store_url': st.session_state.shopify_store, 
            'access_token': st.session_state.shopify_token,
            'sentos_api_url': st.session_state.sentos_api_url, 
            'sentos_api_key': st.session_state.sentos_api_key,
            'sentos_api_secret': st.session_state.sentos_api_secret, 
            'sentos_cookie': st.session_state.sentos_cookie,
            'test_mode': test_mode, 
            'max_workers': max_workers, 
            'sync_mode': sync_mode,
            'progress_callback': st.session_state.progress_queue.put, # Düzeltilmiş satır
            'stop_event': st.session_state.stop_sync_event
        }
        
        thread = threading.Thread(
            target=sync_products_from_sentos_api, 
            kwargs=thread_kwargs, 
            daemon=True
        )
        st.session_state.sync_thread = thread
        thread.start()
        st.rerun()

    st.markdown("---")
    with st.expander("✨ **Feature: Create Missing Products Only**"):
        st.info("This tool compares Sentos with Shopify and only creates products that do not exist in Shopify. It does not update existing products.")
        missing_test_mode = st.checkbox("Test Mode (Scan first 20 products)", value=True, key="missing_test_mode")
        
        if st.button("🚀 Find & Create Missing Products", use_container_width=True, disabled=not sync_ready):
            st.session_state.sync_missing_running = True
            st.session_state.live_log_missing = []
            st.session_state.stop_sync_event = threading.Event()

            # ### DEĞİŞİKLİK BURADA ###
            # Lambda yerine, kuyruğun .put metodunu doğrudan iletiyoruz.
            thread_kwargs = {
                'store_url': st.session_state.shopify_store, 
                'access_token': st.session_state.shopify_token,
                'sentos_api_url': st.session_state.sentos_api_url, 
                'sentos_api_key': st.session_state.sentos_api_key,
                'sentos_api_secret': st.session_state.sentos_api_secret, 
                'sentos_cookie': st.session_state.sentos_cookie,
                'test_mode': missing_test_mode, 
                'max_workers': max_workers,
                'progress_callback': st.session_state.progress_queue.put, # Düzeltilmiş satır
                'stop_event': st.session_state.stop_sync_event
            }
            
            thread = threading.Thread(
                target=sync_missing_products_only, 
                kwargs=thread_kwargs, 
                daemon=True
            )
            st.session_state.missing_sync_thread = thread
            thread.start()
            st.rerun()

    st.markdown("---")
    with st.expander("✨ **Feature: Sync Single Product by SKU**"):
        st.info("Enter the model code (SKU) of a product from Sentos to instantly find and fully update its counterpart in Shopify.")
        sku_to_sync = st.text_input("Model Code (SKU)", placeholder="e.g., V-123-ABC")
        
        if st.button("🔄 Find & Sync Product", use_container_width=True, disabled=not sync_ready):
            if not sku_to_sync:
                st.warning("Please enter an SKU.")
            else:
                with st.spinner(f"Searching and syncing product with SKU '{sku_to_sync}'..."):
                    result = sync_single_product_by_sku(
                        store_url=st.session_state.shopify_store, access_token=st.session_state.shopify_token,
                        sentos_api_url=st.session_state.sentos_api_url, sentos_api_key=st.session_state.sentos_api_key,
                        sentos_api_secret=st.session_state.sentos_api_secret, sentos_cookie=st.session_state.sentos_cookie,
                        sku=sku_to_sync
                    )
                if result.get('success'):
                    st.success(f"✅ Success: {result.get('message')}")
                else:
                    st.error(f"❌ Error: {result.get('message')}")