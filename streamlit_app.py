# streamlit_app.py (Nihai Sürüm - Query Params ile)

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import pandas as pd
from io import StringIO
import os

# Gerekli modülleri import ediyoruz
from config_manager import load_all_user_keys
from data_manager import load_user_data
from shopify_sync import ShopifyAPI, SentosAPI

st.set_page_config(page_title="Vervegrand Sync", page_icon="🔄", layout="wide", initial_sidebar_state="expanded")

def initialize_session_state_defaults():
    defaults = {
        'authentication_status': None,
        'shopify_status': 'pending', 'sentos_status': 'pending',
        'shopify_data': {}, 'sentos_data': {}, 'user_data_loaded_for': None,
        'price_df': None, 'calculated_df': None
    }
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value

def load_and_verify_user_data(username):
    if st.session_state.get('user_data_loaded_for') == username: return
    user_keys = load_all_user_keys(username)
    st.session_state.update(user_keys)
    user_price_data = load_user_data(username)
    try:
        price_df_json = user_price_data.get('price_df_json')
        if price_df_json: st.session_state.price_df = pd.read_json(StringIO(price_df_json), orient='split')
        calculated_df_json = user_price_data.get('calculated_df_json')
        if calculated_df_json: st.session_state.calculated_df = pd.read_json(StringIO(calculated_df_json), orient='split')
    except Exception:
        st.session_state.price_df = None
        st.session_state.calculated_df = None

    if st.session_state.get('shopify_store') and st.session_state.get('shopify_token'):
        try:
            api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
            st.session_state.shopify_data = api.test_connection()
            st.session_state.shopify_status = 'connected'
        except: st.session_state.shopify_status = 'failed'

    if st.session_state.get('sentos_api_url') and st.session_state.get('sentos_api_key') and st.session_state.get('sentos_api_secret'):
        try:
            api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
            st.session_state.sentos_data = api.test_connection()
            st.session_state.sentos_status = 'connected' if st.session_state.sentos_data.get('success') else 'failed'
        except: st.session_state.sentos_status = 'failed'
    st.session_state['user_data_loaded_for'] = username

# --- UYGULAMA BAŞLANGICI ---
# URL'den session_id parametresini kontrol et
if st.query_params.get('session_id') == "active":
    # Eğer URL'de 'session_id=active' varsa, kullanıcıyı giriş yapmış say
    if 'authentication_status' not in st.session_state or not st.session_state.authentication_status:
        st.session_state.authentication_status = True
        # Oturumun ilk kez bu yöntemle kurulduğunu belirtmek için session state'e ek bilgi koyabiliriz.
        st.session_state.name = st.query_params.get('user', 'Kullanıcı') # URL'den kullanıcı adını al
        st.session_state.username = st.query_params.get('username', '')

# --- Ana Logic ---
if st.session_state.get("authentication_status"):
    # Giriş yapılmışsa ana uygulamayı ve kenar çubuğunu göster
    load_and_verify_user_data(st.session_state.get("username"))
    with st.sidebar:
        st.title(f"Hoş geldiniz, *{st.session_state.get('name')}*!")
        if st.button("Logout", use_container_width=True):
            st.session_state.authentication_status = None
            st.session_state.username = None
            st.session_state.name = None
            st.query_params.clear() # URL'den parametreleri temizle
            st.rerun()

    st.info("👈 Lütfen başlamak için kenar çubuğundan bir sayfa seçin.")

else:
    # Giriş yapılmamışsa, authenticator ile giriş formunu göster
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
    )
    authenticator.login()

    if st.session_state["authentication_status"]:
        # Giriş başarılı olduğu anda, URL'yi parametrelerle güncelle ve sayfayı yeniden çalıştır
        st.query_params.session_id = "active"
        st.query_params.user = st.session_state.name
        st.query_params.username = st.session_state.username
        st.rerun()

    elif st.session_state["authentication_status"] is False:
        st.error('Kullanıcı adı/şifre hatalı')
    elif st.session_state["authentication_status"] is None:
        st.warning('Lütfen kullanıcı adı ve şifrenizi girin')