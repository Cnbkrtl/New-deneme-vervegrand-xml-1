# streamlit_app.py (TEŞHİS MODU)

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
import pandas as pd
from io import StringIO
import os # Dosya kontrolü için eklendi

# Diğer importlar
from config_manager import load_all_user_keys
from data_manager import load_user_data
from shopify_sync import ShopifyAPI, SentosAPI

st.set_page_config(page_title="Vervegrand Sync", page_icon="🔄", layout="wide", initial_sidebar_state="expanded")

# --- TEŞHİS FONKSİYONLARI ---
def check_and_display_config():
    """config.yaml dosyasını kontrol eder ve kritik bilgileri ekrana basar."""
    st.warning("--- TEŞHİS BİLGİLERİ (Geliştirici Modu) ---")
    config_path = 'config.yaml'
    if os.path.exists(config_path):
        st.info(f"✅ `{config_path}` dosyası bulundu.")
        try:
            with open(config_path) as file:
                config = yaml.load(file, Loader=SafeLoader)
                cookie_config = config.get('cookie', {})
                cookie_name = cookie_config.get('name', 'BULUNAMADI')
                cookie_key = cookie_config.get('key', 'BULUNAMADI')
                
                st.info(f"📄 Okunan Cookie Adı: `{cookie_name}`")
                st.info(f"🔑 Okunan Cookie Anahtarı (ilk 5 karakter): `{cookie_key[:5]}...`")
                
                if cookie_key == 'BU_KISMI_COK_GUVENLI_VE_RASTGELE_BIR_SEYLE_DEGISTIRIN' or len(cookie_key) < 32:
                     st.error("DİKKAT: Cookie anahtarı (`key`) `config.yaml` içinde güvenli bir değerle değiştirilmemiş gibi görünüyor!")
                return config
        except Exception as e:
            st.error(f"❌ `{config_path}` dosyası okunurken hata oluştu: {e}")
            return None
    else:
        st.error(f"❌ KRİTİK HATA: `{config_path}` dosyası projenin ana dizininde bulunamadı!")
        return None

# --- Normal Fonksiyonlar ---
def initialize_session_state_defaults():
    defaults = { 'authentication_status': None }
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value

def load_and_verify_user_data(username):
    # Bu fonksiyonun içeriği aynı kalabilir...
    pass

# --- UYGULAMA AKIŞI ---

# 1. Önce session state'i başlat
initialize_session_state_defaults()

# 2. Config dosyasını kontrol et ve yükle
config = check_and_display_config()

# 3. Eğer config dosyası okunamadıysa, uygulamayı durdur.
if not config:
    st.error("Uygulama başlatılamıyor. Lütfen yukarıdaki teşhis mesajlarını kontrol edin.")
    st.stop()

# 4. Authenticator'ı başlat
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# 5. Login fonksiyonunu çağır
authenticator.login()

# 6. Session durumunu kontrol et ve ekrana bas
st.info(f"🕵️‍♂️ Session Durumu: `authentication_status` = `{st.session_state.get('authentication_status')}`")

try:
    # Cookie'nin tarayıcıdan okunup okunmadığını kontrol et
    cookie_value = authenticator.cookie_manager.get(authenticator.cookie_name)
    if cookie_value:
        st.info("🍪 Tarayıcıda bir cookie bulundu ve okundu.")
    else:
        st.info("🍪 Tarayıcıda geçerli bir cookie bulunamadı.")
except Exception as e:
    st.error(f"Cookie okunurken bir hata oluştu: {e}")

st.warning("--- TEŞHİS BİLGİLERİ SONU ---")


if st.session_state.get("authentication_status"):
    # load_and_verify_user_data(st.session_state["username"]) # Şimdilik bu kısmı devre dışı bırakalım
    with st.sidebar:
        st.title(f"Hoş geldiniz, *{st.session_state.get('name')}*!")
        authenticator.logout(use_container_width=True)
    
    st.success("🎉 Başarıyla giriş yapıldı!")
    st.balloons()

elif st.session_state.get("authentication_status") is False:
    st.error('Kullanıcı adı/şifre hatalı')

elif st.session_state.get("authentication_status") is None:
    st.warning('Lütfen kullanıcı adı ve şifrenizi girin')