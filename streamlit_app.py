# streamlit_app.py

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import queue
import os

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
/* ... CSS kodunuz ... */
</style>
""", unsafe_allow_html=True)

# --- UYGULAMA BAŞLATMA ---
def initialize_session_state_defaults():
    """Temel session state anahtarlarının var olduğundan emin olur."""
    defaults = {
        'app_initialized': True, 'shopify_status': 'pending', 'sentos_status': 'pending',
        'shopify_data': {}, 'sentos_data': {}, 'sync_running': False,
        'stop_sync_event': None, 'progress_queue': queue.Queue(),
        'sync_results': None, 'live_log': []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

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

# Login widget'ını render et
authenticator.login()

if st.session_state["authentication_status"]:
    # --- Başarılı Giriş Sonrası ---
    
    # Kenar Çubuğu
    with st.sidebar:
        st.title(f"Welcome, *{st.session_state['name']}*!")
        authenticator.logout(use_container_width=True)

        if st.button("Forget All Settings", use_container_width=True, type="primary"):
            if os.path.exists("credentials.enc"): os.remove("credentials.enc")
            if os.path.exists(".secret.key"): os.remove(".secret.key")
            st.success("Tüm ayarlar ve şifreleme anahtarı silindi.")
            st.rerun()
        st.markdown("---")
        st.info("Vervegrand Sync Tool v21.0")

    # Kullanıcıya özel API anahtarlarını yükle ve bağlantıyı test et
    username = st.session_state["username"]
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
    else: st.session_state.shopify_status = 'pending'

    if st.session_state.sentos_api_url and st.session_state.sentos_api_key and st.session_state.sentos_api_secret:
        try:
            sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret)
            st.session_state.sentos_data = sentos_api.test_connection()
            st.session_state.sentos_status = 'connected' if st.session_state.sentos_data.get('success') else 'failed'
        except: st.session_state.sentos_status = 'failed'
    else: st.session_state.sentos_status = 'pending'
    
    # Ana Karşılama Sayfası
    st.markdown("""
        <div class="main-header">
            <h1>Vervegrand Sync Tool</h1>
            <p>Welcome to the main control panel. Please select a page from the sidebar to begin.</p>
        </div>
        """, unsafe_allow_html=True)
    st.info("👈 Please select a page from the sidebar to begin.")

elif st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')