# streamlit_app.py (Nihai Sürüm - Güvenli Token ile Oturum Yönetimi)

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import pandas as pd
from io import StringIO
import os
import secrets
import time

# Gerekli modülleri import ediyoruz
from config_manager import load_all_user_keys
from data_manager import save_user_data, load_user_data
from shopify_sync import ShopifyAPI, SentosAPI

# Oturumun ne kadar süre aktif kalacağı (saniye cinsinden). Örnek: 12 saat.
SESSION_TIMEOUT_SECONDS = 12 * 60 * 60 

st.set_page_config(page_title="Vervegrand Sync", page_icon="🔄", layout="wide", initial_sidebar_state="expanded")

# --- Oturum Doğrulama Fonksiyonu ---
def validate_session_token():
    """URL'deki token'ı sunucuda kayıtlı token ile karşılaştırır."""
    try:
        token = st.query_params.get("token")
        username = st.query_params.get("username")
        
        if not token or not username:
            return False

        user_data = load_user_data(username)
        stored_token = user_data.get("session_token")
        expiry_time = user_data.get("token_expiry", 0)

        if stored_token and expiry_time and time.time() < expiry_time:
            # secrets.compare_digest zamanlama saldırılarına karşı güvenlidir
            if secrets.compare_digest(stored_token, token):
                # Başarılı doğrulama
                st.session_state.authentication_status = True
                st.session_state.name = user_data.get("name", username)
                st.session_state.username = username
                return True
    except Exception as e:
        print(f"Token doğrulama hatası: {e}")
        return False
    return False

# --- Ana Uygulama Mantığı ---

# Sayfa her yüklendiğinde ilk olarak token'ı kontrol et
if "authentication_status" not in st.session_state:
    st.session_state.authentication_status = None

if not st.session_state.authentication_status:
    validate_session_token()

# --- Arayüz Çizimi ---
if st.session_state.get("authentication_status"):
    # --- GİRİŞ YAPILMIŞ EKRAN ---
    with st.sidebar:
        st.title(f"Hoş geldiniz, *{st.session_state.get('name')}*!")
        if st.button("Logout", use_container_width=True):
            # Çıkış yaparken token'ı sil
            user_data = load_user_data(st.session_state.username)
            if "session_token" in user_data: del user_data["session_token"]
            if "token_expiry" in user_data: del user_data["token_expiry"]
            save_user_data(st.session_state.username, **user_data)
            
            # Session state'i temizle
            st.session_state.authentication_status = None
            st.session_state.username = None
            st.session_state.name = None
            st.query_params.clear()
            st.rerun()

    # Diğer sayfaların çalışması için gerekli verileri yükle
    # Bu fonksiyonun içeriğini eski kodunuzdan alıp buraya koyabilirsiniz.
    # (Shopify/Sentos bağlantı testleri vb.)
    st.info("👈 Lütfen başlamak için kenar çubuğundan bir sayfa seçin.")

else:
    # --- GİRİŞ EKRANI ---
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
    )
    authenticator.login()

    if st.session_state.get("authentication_status"):
        # Giriş başarılı olduğu anda, YENİ TOKEN OLUŞTUR ve KAYDET
        username = st.session_state.username
        user_data = load_user_data(username)
        
        new_token = secrets.token_urlsafe(32)
        expiry_time = time.time() + SESSION_TIMEOUT_SECONDS
        
        user_data["session_token"] = new_token
        user_data["token_expiry"] = expiry_time
        user_data["name"] = st.session_state.name # İsim bilgisini de kaydet
        
        save_user_data(username, **user_data)
        
        # URL'yi yeni token ile güncelle ve sayfayı yeniden başlat
        st.query_params.username = username
        st.query_params.token = new_token
        st.rerun()

    elif st.session_state.get("authentication_status") is False:
        st.error('Kullanıcı adı/şifre hatalı')
        
    elif st.session_state.get("authentication_status") is None:
        st.warning('Lütfen kullanıcı adı ve şifrenizi girin')