# 3_sync.py (Sayfa Yenilemeye Dayanıklı Hali)

import streamlit as st
import time
import pandas as pd
from log_manager import save_log
from datetime import timedelta, datetime
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

# Progress tracking functions
def get_sync_progress():
    """Aktif sync'in progress bilgilerini al"""
    if st.session_state.get('sync_job_id'):
        try:
            q = Queue(connection=conn)
            job = q.fetch_job(st.session_state.sync_job_id)
            if job:
                meta = job.meta or {}
                return {
                    'status': job.get_status(),
                    'progress': meta.get('progress', 0),
                    'current_batch': meta.get('current_batch', 0),
                    'total_batches': meta.get('total_batches', 0),
                    'stats': meta.get('stats', {}),
                    'start_time': meta.get('start_time'),
                    'current_product': meta.get('current_product', ''),
                    'total_products': meta.get('total_products', 0),
                    'processed_products': meta.get('processed_products', 0)
                }
        except Exception as e:
            st.error(f"Progress alınamadı: {e}")
    return None

def display_detailed_progress():
    """Detaylı progress bilgilerini göster"""
    progress_data = get_sync_progress()
    
    if not progress_data:
        return
    
    status = progress_data['status']
    progress = progress_data['progress']
    stats = progress_data.get('stats', {})
    start_time = progress_data.get('start_time')
    
    # Ana progress bar
    st.progress(progress / 100 if progress <= 100 else 1.0)
    
    # İstatistik kolonları
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "✅ Güncellenen", 
            stats.get('updated', 0),
            help="Başarıyla güncellenen ürün sayısı"
        )
    
    with col2:
        st.metric(
            "🆕 Yeni Oluşturulan", 
            stats.get('created', 0),
            help="Yeni oluşturulan ürün sayısı"
        )
    
    with col3:
        st.metric(
            "⏭️ Geçilen", 
            stats.get('skipped', 0),
            help="Geçilen/atlanılan ürün sayısı"
        )
    
    with col4:
        st.metric(
            "❌ Başarısız", 
            stats.get('failed', 0),
            help="Hata alan ürün sayısı"
        )
    
    # Zaman bilgileri
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            elapsed = datetime.now() - start_dt.replace(tzinfo=None)
            elapsed_str = str(elapsed).split('.')[0]  # Microseconds'ı kaldır
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("⏱️ Geçen Süre", elapsed_str)
            
            with col2:
                total_products = progress_data.get('total_products', 0)
                processed = progress_data.get('processed_products', 0)
                remaining = max(0, total_products - processed)
                st.metric("📦 Kalan Ürün", f"{remaining}/{total_products}")
            
            with col3:
                # Tahmini kalan süre
                if processed > 0 and remaining > 0:
                    avg_time_per_product = elapsed.total_seconds() / processed
                    estimated_remaining = timedelta(seconds=int(avg_time_per_product * remaining))
                    est_str = str(estimated_remaining).split('.')[0]
                    st.metric("⏳ Tahmini Kalan", est_str)
                else:
                    st.metric("⏳ Tahmini Kalan", "Hesaplanıyor...")
        
        except Exception as e:
            st.warning(f"Zaman hesaplaması hatası: {e}")
    
    # Batch bilgileri
    current_batch = progress_data.get('current_batch', 0)
    total_batches = progress_data.get('total_batches', 0)
    
    if total_batches > 0:
        st.info(f"📋 Batch İlerlemesi: {current_batch}/{total_batches}")
    
    # Şu an işlenen ürün
    current_product = progress_data.get('current_product', '')
    if current_product:
        st.info(f"🔄 Şu an işlenen: {current_product}")
    
    # Status badge
    status_colors = {
        'queued': '🟡',
        'started': '🔵', 
        'finished': '🟢',
        'failed': '🔴',
        'canceled': '⚫'
    }
    
    status_icon = status_colors.get(status, '⚪')
    st.info(f"{status_icon} Durum: {status.upper()}")

# Ana sync sayfası
def main():
    st.title("🔄 Ürün Senkronizasyonu")
    
    # Aktif sync kontrolü
    active_sync = st.session_state.get('sync_status') == 'running'
    
    if active_sync:
        st.success("🔄 Aktif senkronizasyon devam ediyor!")
        
        # Detaylı progress göster
        display_detailed_progress()
        
        # Kontrol butonları
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Durumu Yenile", key="refresh_status"):
                st.rerun()
        
        with col2:
            if st.button("⏹️ Sync'i Durdur", key="stop_sync"):
                try:
                    q = Queue(connection=conn)
                    job = q.fetch_job(st.session_state.sync_job_id)
                    if job:
                        job.cancel()
                        st.session_state.sync_status = 'cancelled'
                        st.session_state.sync_job_id = None
                        st.success("Sync durduruldu!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sync durdurulamadı: {e}")
        
        with col3:
            # Auto-refresh toggle
            auto_refresh = st.checkbox("🔄 Otomatik Yenileme", value=True)
            
        # Auto-refresh
        if auto_refresh:
            time.sleep(3)
            st.rerun()
            
    else:
        # Sync form (existing sync_page functionality)
        display_sync_form()

def display_sync_form():
    """Sync form'unu göster"""
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