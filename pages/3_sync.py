# 3_sync.py (Sayfa Yenilemeye Dayanıklı Hali)

import streamlit as st
import time
import pandas as pd
from log_manager import save_log
from datetime import timedelta
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
import os

# --- Session State Başlatma ---
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
if 'sync_job_id' not in st.session_state:
    st.session_state.sync_job_id = None
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = None

# --- Redis Bağlantısı ---
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
try:
    conn = Redis.from_url(redis_url)
    conn.ping()
    q = Queue(connection=conn)
    redis_connected = True
except Exception as e:
    st.error(f"Redis sunucusuna bağlanılamadı: {e}. Worker'lar çalışmayacak.")
    redis_connected = False
    
# --- Giriş Kontrolü ---
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- YENİ: SAYFA YENİLENDİĞİNDE ÇALIŞAN İŞİ KONTROL ETME ---
# Bu blok, sayfa her yüklendiğinde çalışır ve yarım kalmış bir iş var mı diye bakar.
if st.session_state.sync_job_id and not st.session_state.sync_running:
    try:
        job = Job.fetch(st.session_state.sync_job_id, connection=conn)
        status = job.get_status()
        # Eğer iş hala çalışıyor veya kuyruktaysa, takip modunu tekrar aktif et.
        if status in ['queued', 'started', 'deferred']:
            st.session_state.sync_running = True
            st.warning("Devam eden bir senkronizasyon tespit edildi. Takip ediliyor...")
        # Eğer iş bitmiş veya hata vermişse, session state'i temizle.
        else:
            st.session_state.sync_running = False
            st.session_state.sync_job_id = None
    except NoSuchJobError:
        # Eğer Redis'te böyle bir iş yoksa (çoktan bitmiş ve silinmiş olabilir), state'i temizle.
        st.session_state.sync_running = False
        st.session_state.sync_job_id = None

# --- Sayfa Başlığı ---
st.markdown("""
<div class="main-header">
    <h1>🚀 Sync Products</h1>
    <p>Start, monitor, and review synchronization tasks between Sentos and Shopify.</p>
</div>
""", unsafe_allow_html=True)

# --- ARAYÜZ MANTIĞI ---
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected' and
              redis_connected)

if not sync_ready and not st.session_state.sync_running:
    if not redis_connected:
        st.warning("⚠️ Redis bağlantısı kurulamadığı için senkronizasyon başlatılamaz.")
    else:
        st.warning("⚠️ Please configure and test both API connections in Settings before starting a sync.")

# Eğer senkronizasyon çalışmıyorsa başlatma seçeneklerini göster
if not st.session_state.sync_running:
    st.subheader("Start a New Sync Task")
    
    sync_mode = st.selectbox("Select Sync Type", ["Full Sync (Create & Update All)", "Stock & Variants Only", "Images Only", "Images with SEO Alt Text", "Descriptions Only", "Categories (Product Type) Only"])
    test_mode = st.checkbox("Test Mode (Sync first 20 products)", value=True)
    max_workers = st.number_input("Concurrent Workers", min_value=1, max_value=10, value=3)

    if st.button("🚀 Start Sync", type="primary", use_container_width=True, disabled=not sync_ready):
        st.session_state.sync_running = True
        st.session_state.sync_results = None
        st.session_state.start_time = time.monotonic()
        
        try:
            from shopify_sync import sync_products_from_sentos_api
            
            job = q.enqueue(
                sync_products_from_sentos_api,
                args=(
                    st.session_state.shopify_store, st.session_state.shopify_token,
                    st.session_state.sentos_api_url, st.session_state.sentos_api_key,
                    st.session_state.sentos_api_secret, st.session_state.sentos_cookie,
                    test_mode,
                    max_workers,
                    sync_mode
                ),
                job_timeout='2h',
                result_ttl=86400 
            )
            st.session_state.sync_job_id = job.id
            st.info(f"Sync task has been sent to the worker queue. Job ID: {job.id}")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to enqueue sync task: {e}")
            st.session_state.sync_running = False

# Eğer senkronizasyon çalışıyorsa takip ekranını göster
if st.session_state.sync_running:
    st.subheader("📊 Sync in Progress...")
    
    if st.button("🛑 Stop Sync", use_container_width=True):
        if st.session_state.sync_job_id:
            try:
                job = Job.fetch(st.session_state.sync_job_id, connection=conn)
                job.meta['stop_requested'] = True
                job.save_meta()
                st.warning("Stop signal sent. Waiting for the current tasks to finish...")
            except NoSuchJobError:
                st.error("Job could not be found to stop.")
                st.session_state.sync_running = False
                st.rerun()
    
    st.markdown("---")

    progress_bar = st.progress(0, text="Connecting to worker...")
    stats_placeholder = st.empty()
    log_expander = st.expander("Show Live Product Log", expanded=True)
    with log_expander:
        log_placeholder = st.empty()
    
    while st.session_state.sync_running:
        try:
            job = Job.fetch(st.session_state.sync_job_id, connection=conn)
            status = job.get_status()
            update = job.meta or {}

            if status == 'finished':
                st.session_state.sync_results = job.result
                st.session_state.sync_running = False
                st.session_state.sync_job_id = None
                st.success("Job finished successfully.")
                break
            
            if status == 'failed':
                st.session_state.sync_results = {
                    'stats': update.get('stats', {}), 
                    'details': [{'status': 'error', 'reason': job.exc_info}]
                }
                st.session_state.sync_running = False
                st.session_state.sync_job_id = None
                st.error(f"Job failed! Check worker logs for details.")
                break

            progress_bar.progress(update.get('progress', 0) / 100.0, text=update.get('message', 'Processing...'))

            if 'stats' in update:
                stats = update['stats']
                with stats_placeholder.container():
                    st.metric("Total Products", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
                    kpi_cols = st.columns(4)
                    kpi_cols[0].metric("✅ Created", stats.get('created', 0))
                    kpi_cols[1].metric("🔄 Updated", stats.get('updated', 0))
                    kpi_cols[2].metric("❌ Failed", stats.get('failed', 0))
                    kpi_cols[3].metric("⏭️ Skipped", stats.get('skipped', 0))

            if 'live_log' in update:
                live_log_html = "".join(reversed(update['live_log'][-50:]))
                with log_placeholder.container():
                    st.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{live_log_html}</div>', unsafe_allow_html=True)
            
            time.sleep(2)

        except NoSuchJobError:
            st.error("Sync job not found in queue. It may have expired.")
            st.session_state.sync_running = False
            break
        except Exception as e:
            st.error(f"An unexpected error occurred while monitoring the job: {e}")
            st.session_state.sync_running = False
            break
    
    if not st.session_state.sync_running:
        st.rerun()

if st.session_state.sync_results:
    st.subheader("✅ Sync Task Completed")
    results = st.session_state.sync_results
    stats = results.get('stats', {})
    
    if results and stats:
        duration = results.get('duration', 'N/A')
        st.success(f"The synchronization task finished in {duration}. See the summary below.")
        
        results['sync_mode'] = st.session_state.get('selected_sync_mode', 'N/A')
        save_log(results)

    st.metric("Total Products Processed", f"{stats.get('processed', 0)} / {stats.get('total', 0)}")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("✅ Created", stats.get('created', 0))
    kpi_cols[1].metric("🔄 Updated", stats.get('updated', 0))
    kpi_cols[2].metric("❌ Failed", stats.get('failed', 0))
    kpi_cols[3].metric("⏭️ Skipped", stats.get('skipped', 0))
    
    with st.expander("View Detailed Log", expanded=False):
        details = results.get('details', [])
        if details:
            if isinstance(details[0], str):
                st.error(details[0])
            else:
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)