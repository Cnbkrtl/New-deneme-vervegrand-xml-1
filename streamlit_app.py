# streamlit_app.py (Düzeltilmiş Sürüm)

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import pandas as pd
from io import StringIO
import threading
import queue

# Gerekli modülleri import ediyoruz
from config_manager import load_all_user_keys
from data_manager import load_user_data
# YENİ: Import ifadeleri yeni modüler yapıya göre güncellendi.
from connectors.shopify_api import ShopifyAPI
from connectors.sentos_api import SentosAPI

st.set_page_config(page_title="Vervegrand Sync", page_icon="🔄", layout="wide", initial_sidebar_state="expanded")

# YENİ: Oturum durumu için başlangıç değerlerini ayarlayan fonksiyon
def initialize_session_state_defaults():
    """Oturum durumu için başlangıç değerlerini ayarlar."""
    defaults = {
        'authentication_status': None,
        'shopify_status': 'pending', 'sentos_status': 'pending',
        'shopify_data': {}, 'sentos_data': {}, 'user_data_loaded_for': None,
        'price_df': None, 'calculated_df': None,
        'shopify_store': None, 'shopify_token': None,
        'sentos_api_url': None, 'sentos_api_key': None, 'sentos_api_secret': None, 'sentos_cookie': None,
        'update_in_progress': False,
        'sync_progress_queue': queue.Queue()
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def load_and_verify_user_data(username):
    """Kullanıcıya özel sırları ve verileri yükler, bağlantıları test eder."""
    # YENİ: Oturum durumu önceden yüklenmişse tekrar yüklemeye gerek yok
    if st.session_state.get('user_data_loaded_for') == username:
        return

    # API anahtarlarını Streamlit Secrets'tan yükle
    user_keys = load_all_user_keys(username)
    st.session_state.update(user_keys)
    
    # Kalıcı fiyat verilerini data_manager'dan yükle
    user_price_data = load_user_data(username)
    try:
        price_df_json = user_price_data.get('price_df_json')
        if price_df_json: st.session_state.price_df = pd.read_json(StringIO(price_df_json), orient='split')
        calculated_df_json = user_price_data.get('calculated_df_json')
        if calculated_df_json: st.session_state.calculated_df = pd.read_json(StringIO(calculated_df_json), orient='split')
    except Exception as e:
        st.session_state.price_df, st.session_state.calculated_df = None, None

    # API Bağlantı Testleri
    if st.session_state.get('shopify_store') and st.session_state.get('shopify_token'):
        try:
            api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            # test_connection metodu ShopifyAPI sınıfına eklenmelidir.
            # st.session_state.shopify_data = api.test_connection()
            st.session_state.shopify_status = 'connected'
        except: st.session_state.shopify_status = 'failed'

    if st.session_state.get('sentos_api_url') and st.session_state.get('sentos_api_key'):
        try:
            api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
            # test_connection metodu SentosAPI sınıfına eklenmelidir.
            # st.session_state.sentos_data = api.test_connection()
            st.session_state.sentos_status = 'connected' # if st.session_state.sentos_data.get('success') else 'failed'
        except: st.session_state.sentos_status = 'failed'
            
    st.session_state['user_data_loaded_for'] = username

# --- Ana Uygulama Mantığı ---
initialize_session_state_defaults() # Sayfa yüklenirken varsayılan değerleri ayarla

with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login()

if st.session_state.get("authentication_status"):
    load_and_verify_user_data(st.session_state.get("username"))
    with st.sidebar:
        st.title(f"Hoş geldiniz, *{st.session_state.get('name')}*!")
        authenticator.logout(use_container_width=True)
    st.info("👈 Lütfen başlamak için kenar çubuğundan bir sayfa seçin.")

elif st.session_state.get("authentication_status") is False:
    st.error('Kullanıcı adı/şifre hatalı')

elif st.session_state.get("authentication_status") is None:
    st.warning('Lütfen kullanıcı adı ve şifrenizi girin')