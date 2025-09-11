# pages/2_settings.py (Güncellenmiş Sürüm)

import streamlit as st
import json
# YENİ: Modüler yapıya uygun olarak import yolları güncellendi.
from connectors.shopify_api import ShopifyAPI
from connectors.sentos_api import SentosAPI

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# --- Giriş Kontrolü ve Sayfa Kurulumu ---
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

load_css()

# --- AYARLAR SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>⚙️ Ayarlar & Bağlantı Durumu</h1>
    <p>Mevcut API ayarları aşağıda listelenmiştir. Bu ayarlar Streamlit Cloud üzerinden yönetilmektedir.</p>
</div>
""", unsafe_allow_html=True)

st.info("💡 Buradaki tüm bilgiler, uygulamanızın Streamlit Cloud'daki 'Secrets' bölümünden okunmaktadır. Değişikliklerin kalıcı olması için sırlarınızı oradan yönetmelisiniz.")

# --- Ayar Görüntüleme Bölümü ---
with st.container(border=True):
    st.subheader("🔗 Mevcut API Ayarları")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<h5>🏪 Shopify Ayarları</h5>", unsafe_allow_html=True)
        st.text_input("Mağaza URL", value=st.session_state.get('shopify_store', 'Değer Bulunamadı'), disabled=True)
        st.text_input("Erişim Token'ı", value="********" if st.session_state.get('shopify_token') else 'Değer Bulunamadı', type="password", disabled=True)
    
    with col2:
        st.markdown("<h5><img src='https://api.sentos.com.tr/img/favicon.png' width=20> Sentos API Ayarları</h5>", unsafe_allow_html=True)
        st.text_input("Sentos API URL", value=st.session_state.get('sentos_api_url', 'Değer Bulunamadı'), disabled=True)
        st.text_input("Sentos API Key", value=st.session_state.get('sentos_api_key', 'Değer Bulunamadı'), disabled=True)
        st.text_input("Sentos API Secret", value="********" if st.session_state.get('sentos_api_secret') else 'Değer Bulunamadı', type="password", disabled=True)
        st.text_input("Sentos API Cookie", value="********" if st.session_state.get('sentos_cookie') else 'Değer Bulunamadı', type="password", disabled=True)

with st.container(border=True):
    st.subheader("📊 Google E-Tablolar Entegrasyonu")
    gcp_json = st.session_state.get('gcp_service_account_json', '')
    if gcp_json:
        try:
            client_email = json.loads(gcp_json).get('client_email', 'JSON formatı hatalı')
            st.success(f"✅ Google Service Account anahtarı yüklendi. (Hesap: {client_email})")
        except json.JSONDecodeError:
            st.error("❌ Yüklenen Google Service Account anahtarı geçerli bir JSON formatında değil.")
    else:
        st.warning("⚠️ Google Service Account anahtarı Streamlit Secrets'ta bulunamadı.")

st.markdown("---")

# --- Bağlantı Testi Bölümü ---
st.subheader("🧪 Bağlantı Testleri")
if st.button("🔄 Tüm Bağlantıları Yeniden Test Et", use_container_width=True, type="primary"):
    with st.spinner("Bağlantılar test ediliyor..."):
        # Shopify Testi
        shopify_store = st.session_state.get('shopify_store')
        shopify_token = st.session_state.get('shopify_token')
        if shopify_store and shopify_token:
            try:
                api = ShopifyAPI(shopify_store, shopify_token)
                # NOT: ShopifyAPI sınıfında test_connection metodu bulunmadığı için geçici olarak kapatıldı.
                # Gerekirse bu metot ShopifyAPI sınıfına eklenebilir.
                result = api.test_connection()
                st.session_state.shopify_status = 'connected'
                st.session_state.shopify_data = result
                st.success(f"✅ Shopify bağlantısı başarılı!")
            except Exception as e:
                st.session_state.shopify_status = 'failed'
                st.error(f"❌ Shopify Bağlantısı kurulamadı: {e}")
        else:
            st.warning("Shopify bilgileri eksik, test edilemedi.")

        # Sentos Testi
        sentos_url = st.session_state.get('sentos_api_url')
        sentos_key = st.session_state.get('sentos_api_key')
        sentos_secret = st.session_state.get('sentos_api_secret')
        sentos_cookie = st.session_state.get('sentos_cookie')
        if sentos_url and sentos_key:
            try:
                api = SentosAPI(sentos_url, sentos_key, sentos_secret, sentos_cookie)
                # NOT: SentosAPI sınıfında test_connection metodu bulunmadığı için geçici olarak kapatıldı.
                # Gerekirse bu metot SentosAPI sınıfına eklenebilir.
                result = api.test_connection()
                st.session_state.sentos_status = 'connected'
                st.session_state.sentos_data = result
                st.success(f"✅ Sentos bağlantısı başarılı!")
            except Exception as e:
                st.session_state.sentos_status = 'failed'
                st.error(f"❌ Sentos Bağlantısı kurulamadı: {e}")
        else:
            st.warning("Sentos bilgileri eksik, test edilemedi.")