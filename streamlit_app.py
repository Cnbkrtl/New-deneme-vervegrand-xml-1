# streamlit_app.py

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import queue
import os
import redis
import json
from rq import Queue
from datetime import datetime

from config_manager import load_all_keys
from shopify_sync import ShopifyAPI, SentosAPI

# --- Sayfa Yapılandırması ---
st.set_page_config(
    page_title="Vervegrand Sync",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Stil Dosyası (Değişiklik yok) ---
st.markdown("""
<style>
/* ... CSS kodunuz burada ... */
</style>
""", unsafe_allow_html=True)


def initialize_session_state_defaults():
    defaults = {
        'app_initialized': True, 'shopify_status': 'pending', 'sentos_status': 'pending',
        'shopify_data': {}, 'sentos_data': {}, 'sync_running': False,
        'stop_sync_event': None, 'progress_queue': queue.Queue(),
        'sync_results': None, 'live_log': [], 'user_data_loaded_for': None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def load_and_verify_user_data(username):
    """Kullanıcıya özel API anahtarlarını yükler ve bağlantıları test eder."""
    # Bu fonksiyon, aynı oturumda tekrar tekrar çalışıp API'leri yormasın diye bir kontrol ekliyoruz.
    if st.session_state.get('user_data_loaded_for') == username:
        return

    st.session_state.shopify_status = 'pending'
    st.session_state.sentos_status = 'pending'

    all_creds = load_all_keys()
    user_creds = all_creds.get(username, {})

    # API anahtarlarını session_state'e yükle
    st.session_state.shopify_store = user_creds.get('shopify_store')
    st.session_state.shopify_token = user_creds.get('shopify_token')
    st.session_state.sentos_api_url = user_creds.get('sentos_api_url')
    st.session_state.sentos_api_key = user_creds.get('sentos_api_key')
    st.session_state.sentos_api_secret = user_creds.get('sentos_api_secret')
    st.session_state.sentos_cookie = user_creds.get('sentos_cookie')

    # Bağlantıları test et
    if st.session_state.shopify_store and st.session_state.shopify_token:
        try:
            shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            st.session_state.shopify_data = shopify_api.test_connection()
            st.session_state.shopify_status = 'connected'
        except: st.session_state.shopify_status = 'failed'

    if st.session_state.sentos_api_url and st.session_state.sentos_api_key and st.session_state.sentos_api_secret:
        try:
            sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret)
            st.session_state.sentos_data = sentos_api.test_connection()
            st.session_state.sentos_status = 'connected' if st.session_state.sentos_data.get('success') else 'failed'
        except: st.session_state.sentos_status = 'failed'

    # Bu kullanıcı için verilerin yüklendiğini işaretle
    st.session_state['user_data_loaded_for'] = username


initialize_session_state_defaults()

# --- GİRİŞ VE KULLANICI YÖNETİMİ ---
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login()

if st.session_state["authentication_status"]:
    # YENİ ve GÜVENİLİR YÖNTEM:
    # Kullanıcı giriş yaptığı sürece, anahtarlarının yüklendiğinden emin ol.
    load_and_verify_user_data(st.session_state["username"])

    with st.sidebar:
        st.title(f"Welcome, *{st.session_state['name']}*!")
        authenticator.logout(use_container_width=True)

        if st.button("Forget All Settings", use_container_width=True, type="primary"):
            if os.path.exists("credentials.enc"): os.remove("credentials.enc")
            if os.path.exists(".secret.key"): os.remove(".secret.key")
            st.success("Tüm ayarlar ve şifreleme anahtarı silindi.")
            st.rerun()
        st.markdown("---")
        st.info("Vervegrand Sync Tool v21.1")

    st.markdown("""
        <div class="main-header">
            <h1>Vervegrand Sync Tool</h1>
            <p>Welcome to the main control panel. Please select a page from the sidebar to begin.</p>
        </div>
        """, unsafe_allow_html=True)
    st.info("👈 Please select a page from the sidebar to begin.")

    import streamlit as st

    # Redis connection setup
    @st.cache_resource
    def get_redis_connection():
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        return redis.from_url(redis_url)

    @st.cache_resource
    def get_queue():
        r = get_redis_connection()
        return Queue('default', connection=r)

    # Sync başlatırken
    def start_sync():
        q = get_queue()
        
        # Job oluştur ve ID'yi al
        job = q.enqueue(
            # sync fonksiyonu ve parametreleri
        )
        
        st.session_state.sync_status = "running"
        st.session_state.sync_job_id = job.id  # job.id kullan
        st.session_state.sync_progress = 0

    def save_sync_state_to_redis(state_data):
        """Sync durumunu Redis'e kaydet (cross-device için)"""
        try:
            r = get_redis_connection()
            r.setex('global_sync_state', 3600, json.dumps(state_data))  # 1 saat expire
        except Exception as e:
            st.error(f"Sync durumu kaydedilemedi: {e}")

    def load_sync_state_from_redis():
        """Redis'ten sync durumunu yükle"""
        try:
            r = get_redis_connection()
            state_json = r.get('global_sync_state')
            if state_json:
                return json.loads(state_json)
        except Exception as e:
            st.warning(f"Sync durumu yüklenemedi: {e}")
        return None

    # Session state initialization with Redis sync
    def initialize_session_state():
        # Önce Redis'ten global durumu kontrol et
        global_state = load_sync_state_from_redis()
        
        if global_state and global_state.get('sync_status') == 'running':
            # Global aktif sync varsa session state'i güncelle
            st.session_state.sync_status = global_state['sync_status']
            st.session_state.sync_job_id = global_state.get('sync_job_id')
            st.session_state.sync_start_time = global_state.get('sync_start_time')
        else:
            # Local session state'i kontrol et
            if 'sync_status' not in st.session_state:
                st.session_state.sync_status = None
            if 'sync_job_id' not in st.session_state:
                st.session_state.sync_job_id = None
            if 'sync_start_time' not in st.session_state:
                st.session_state.sync_start_time = None

    # Ana sayfa başında bu fonksiyonu çağır
    initialize_session_state()

    # Sync başlatma fonksiyonu güncellemesi
    def start_sync_with_redis_state(job_id):
        """Sync başlatır ve durumu Redis'e kaydeder"""
        state_data = {
            'sync_status': 'running',
            'sync_job_id': job_id,
            'sync_start_time': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat()
        }
        
        # Session state güncelle
        st.session_state.sync_status = state_data['sync_status']
        st.session_state.sync_job_id = state_data['sync_job_id']
        st.session_state.sync_start_time = state_data['sync_start_time']
        
        # Redis'e kaydet
        save_sync_state_to_redis(state_data)

    # Progress tracking function
    def check_sync_progress():
        if st.session_state.sync_job_id:
            q = get_queue()  # Queue'yu burada tanımla
            # Redis job durumunu kontrol et
            job = q.fetch_job(st.session_state.sync_job_id)
            if job:
                if job.is_finished:
                    st.session_state.sync_status = "completed"
                elif job.is_failed:
                    st.session_state.sync_status = "failed"
                else:
                    st.session_state.sync_status = "running"
                    # Progress güncelle
                    st.session_state.sync_progress = job.meta.get('progress', 0)

    # Progress tracking with Redis
    def update_sync_progress_in_redis():
        """Sync progress'ini Redis'e güncelle"""
        if st.session_state.get('sync_job_id'):
            try:
                q = get_queue()
                job = q.fetch_job(st.session_state.sync_job_id)
                if job:
                    status = job.get_status()
                    
                    # Status değişti mi kontrol et
                    if status != 'started':
                        state_data = {
                            'sync_status': 'completed' if status == 'finished' else 'failed',
                            'sync_job_id': None,
                            'sync_start_time': None,
                            'last_update': datetime.now().isoformat()
                        }
                        
                        # Session state temizle
                        st.session_state.sync_status = None
                        st.session_state.sync_job_id = None
                        
                        # Redis'i güncelle
                        save_sync_state_to_redis(state_data)
                        
            except Exception as e:
                st.error(f"Progress güncellenirken hata: {e}")

    # Her sayfada sync durumunu kontrol et
    if st.session_state.sync_status == "running":
        check_sync_progress()

    # Her sayfa yüklendiğinde progress'i kontrol et
    if st.session_state.get('sync_status') == 'running':
        update_sync_progress_in_redis()

    # Sync durumunu sidebar'da göster
    if st.session_state.sync_status == "running":
        st.sidebar.warning(f"🔄 Sync devam ediyor... ({st.session_state.sync_progress}%)")
    elif st.session_state.sync_status == "completed":
        st.sidebar.success("✅ Sync tamamlandı!")
    elif st.session_state.sync_status == "failed":
        st.sidebar.error("❌ Sync başarısız!")

elif st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')