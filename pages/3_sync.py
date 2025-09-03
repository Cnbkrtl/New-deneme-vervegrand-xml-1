import streamlit as st
import os
from redis import Redis
from rq import Queue
from shopify_sync import sync_products_from_sentos_api # Görevi bu fonksiyona göndereceğiz

# --- Giriş Kontrolü ---
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- Redis Bağlantısı ---
# worker.py'deki ile aynı mantık
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
try:
    redis_conn = Redis.from_url(redis_url)
    q = Queue(connection=redis_conn)
    redis_available = True
except Exception as e:
    redis_available = False
    st.error(f"Redis sunucusuna bağlanılamadı: {e}")
    st.info("Lütfen Redis sunucusunun çalıştığından ve bağlantı bilgilerinin doğru olduğundan emin olun.")

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
              redis_available)

if sync_ready:
    st.success("API connections are active and the system is ready to sync.")
    
    sync_mode = st.radio(
        "Select Synchronization Mode:",
        ('Update Existing & Add New', 'Only Add New Products', 'Only Update Existing'),
        key="sync_mode_selection",
        horizontal=True
    )

    if st.button("🚀 Start Synchronization", type="primary", use_container_width=True):
        with st.spinner("Sending sync job to the background worker..."):
            # Gerekli API bilgilerini session'dan alıyoruz
            credentials = {
                "shopify_store": st.session_state.get('shopify_store'),
                "shopify_token": st.session_state.get('shopify_token'),
                "sentos_api_url": st.session_state.get('sentos_api_url'),
                "sentos_api_key": st.session_state.get('sentos_api_key'),
                "sentos_api_secret": st.session_state.get('sentos_api_secret'),
                "sentos_cookie": st.session_state.get('sentos_cookie')
            }
            
            # sync_products_from_sentos_api fonksiyonunu görev olarak kuyruğa ekliyoruz.
            # Artık progress_callback göndermiyoruz çünkü worker'ın arayüzle doğrudan iletişimi yok.
            job = q.enqueue(
                sync_products_from_sentos_api,
                credentials,
                sync_mode,
                progress_callback=None # Bu artık kullanılmıyor
            )
            
            st.success(f"Sync job has been successfully queued! Job ID: {job.id}")
            st.info("The process will run in the background. You can now safely refresh or close this page. You can check the logs page for results later.")
            
else:
    st.warning("Cannot start sync. Please ensure both Shopify and Sentos connections are active on the Dashboard and Redis is running.")

st.markdown("---")
st.subheader("Current Queue Status")
if redis_available:
    st.metric("Jobs in Queue", len(q))
    # Gelecekte buraya çalışan ve biten görevleri gösteren daha detaylı bir tablo ekleyebiliriz.
else:
    st.metric("Jobs in Queue", "N/A")