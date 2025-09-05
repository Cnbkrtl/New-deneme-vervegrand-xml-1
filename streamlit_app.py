import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
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

# --- CSS Stil Dosyası ---
st.markdown("""
<style>
/* ... CSS kodunuz burada kalabilir ... */
</style>
""", unsafe_allow_html=True)


def initialize_session_state_defaults():
    """Oturum durumu için başlangıç değerlerini ayarlar."""
    defaults = {
        'shopify_status': 'pending', 'sentos_status': 'pending',
        'shopify_data': {}, 'sentos_data': {},
        'user_data_loaded_for': None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def load_and_verify_user_data(username):
    """Kullanıcıya özel API anahtarlarını yükler ve bağlantıları test eder."""
    if st.session_state.get('user_data_loaded_for') == username:
        return # Veriler zaten yüklüyse tekrar çalıştırma

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
    # --- EKSİK SATIR BURAYA EKLENDİ ---
    st.session_state.gcp_service_account_json = user_creds.get('gcp_service_account_json')

    # Bağlantıları test et
    if st.session_state.shopify_store and st.session_state.shopify_token:
        try:
            api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            st.session_state.shopify_data = api.test_connection()
            st.session_state.shopify_status = 'connected'
        except: st.session_state.shopify_status = 'failed'

    if st.session_state.sentos_api_url and st.session_state.sentos_api_key and st.session_state.sentos_api_secret:
        try:
            api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
            st.session_state.sentos_data = api.test_connection()
            st.session_state.sentos_status = 'connected' if st.session_state.sentos_data.get('success') else 'failed'
        except: st.session_state.sentos_status = 'failed'

    st.session_state['user_data_loaded_for'] = username


# --- Uygulama Başlangıcı ---
initialize_session_state_defaults()

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
    # Kullanıcı giriş yaptığında, API anahtarlarını yükle ve doğrula
    load_and_verify_user_data(st.session_state["username"])

    with st.sidebar:
        st.title(f"Hoş geldiniz, *{st.session_state['name']}*!")
        authenticator.logout(use_container_width=True)
        st.markdown("---")
        st.info("Vervegrand Sync Tool v22.0 (Cloud Edition)")

    # Ana Sayfa İçeriği
    st.markdown("""
        <div class="main-header">
            <h1>Vervegrand Sync Tool</h1>
            <p>Panele hoş geldiniz. Lütfen kenar çubuğundan bir sayfa seçin.</p>
        </div>
        """, unsafe_allow_html=True)
    st.info("👈 Lütfen başlamak için kenar çubuğundan **Ayarlar** veya **Senkronizasyon** sayfasını seçin.")

elif st.session_state["authentication_status"] is False:
    st.error('Kullanıcı adı/şifre hatalı')
elif st.session_state["authentication_status"] is None:
    st.warning('Lütfen kullanıcı adı ve şifrenizi girin')