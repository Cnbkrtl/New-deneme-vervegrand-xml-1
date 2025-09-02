# streamlit_app.py

import streamlit as st
import os
import queue
from config_manager import load_all_keys
from shopify_sync import ShopifyAPI, SentosAPI # Doğru import burada

# --- Sayfa Yapılandırması ---
st.set_page_config(
    page_title="Vervegrand Sync",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Stil Dosyası ---
st.markdown("""
<style>
    /* ... CSS kodunuz burada, değişiklik yok ... */
</style>
""", unsafe_allow_html=True)

# --- UYGULAMA BAŞLATMA VE DEĞİŞKEN TANIMLAMA ---
def initialize_app_state():
    """
    Uygulama ilk çalıştığında veya oturum sıfırlandığında tüm state değişkenlerini
    merkezi olarak başlatır. Bu 'AttributeError' hatalarını önler.
    """
    if 'app_initialized' in st.session_state:
        return

    st.session_state.app_initialized = True
    st.session_state.logged_in = False
    st.session_state.username = ""
    
    # API Durumları
    st.session_state.shopify_status = 'pending'
    st.session_state.sentos_status = 'pending'
    st.session_state.shopify_data = {}
    st.session_state.sentos_data = {}
    
    # Sync Sayfası için gerekli değişkenler
    st.session_state.sync_running = False
    st.session_state.stop_sync_event = None
    st.session_state.progress_queue = queue.Queue()
    st.session_state.sync_results = None
    st.session_state.live_log = []
    
    # Kayıtlı kimlik bilgilerini yükle ve bağlantıları test et
    credentials = load_all_keys()
    if credentials:
        st.session_state.update(credentials)
        st.session_state.logged_in = True
        st.session_state.username = "admin"

        # Otomatik bağlantı testleri (uygulama açılışında)
        if st.session_state.get('shopify_store') and st.session_state.get('shopify_token'):
            try:
                shopify_api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                st.session_state.shopify_data = shopify_api.test_connection()
                st.session_state.shopify_status = 'connected'
            except Exception:
                st.session_state.shopify_status = 'failed'
        
        if st.session_state.get('sentos_api_url') and st.session_state.get('sentos_api_key') and st.session_state.get('sentos_api_secret'):
            try:
                # DÜZELTME: SentOSAPI -> SentosAPI olarak düzeltildi.
                sentos_api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret)
                st.session_state.sentos_data = sentos_api.test_connection()
                st.session_state.sentos_status = 'connected'
            except Exception:
                st.session_state.sentos_status = 'failed'

# Uygulama durumunu başlat
initialize_app_state()

# --- GİRİŞ KONTROLÜ VE ANA UYGULAMA MANTIĞI ---
if not st.session_state.get("logged_in"):
    st.markdown("""
    <div class="main-header">
        <h1>🔐 Admin Login</h1>
        <p>Please enter your credentials to access the sync tool.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("ID", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            correct_username = st.secrets.get("ADMIN_USERNAME", "admin")
            correct_password = st.secrets.get("ADMIN_PASSWORD", "19519")
            if username == correct_username and password == correct_password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Incorrect ID or password.")
else:
    # Kenar çubuğu
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.get('username', 'Admin')}!")
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key != 'app_initialized':
                    del st.session_state[key]
            st.rerun()

        if st.button("Forget All Settings", use_container_width=True, type="primary"):
            if os.path.exists("credentials.enc"): os.remove("credentials.enc")
            if os.path.exists(".secret.key"): os.remove(".secret.key")
            for key in list(st.session_state.keys()):
                 if key != 'app_initialized':
                    del st.session_state[key]
            st.rerun()
        st.markdown("---")
        st.info("Vervegrand Sync Tool v20.5")

    # Ana Karşılama Sayfası
    st.markdown("""
        <div class="main-header">
            <h1>Vervegrand Sync Tool</h1>
            <p>Welcome to the main control panel. Please select a page from the sidebar to begin.</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.info("👈 Please select a page from the sidebar to begin.")