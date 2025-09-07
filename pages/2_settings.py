# pages/2_settings.py

import streamlit as st
import json
from shopify_sync import ShopifyAPI, SentosAPI

# İYİLEŞTİRME: config_manager.py artık sırlar st.secrets'ten yönetildiği için
# bir kaydetme fonksiyonuna ihtiyaç duymuyor. Bu nedenle bu import kaldırıldı.

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass # Ana sayfada uyarı zaten gösterilir

# --- Giriş Kontrolü ve Sayfa Kurulumu ---
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

load_css()

# --- AYARLAR SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>⚙️ Ayarlar & Bağlantı Testi</h1>
    <p>Bu arayüzdeki ayarlar yalnızca mevcut oturum için geçerlidir.
    Kalıcı değişiklikler için Streamlit Cloud Secrets bölümünü güncellemelisiniz.</p>
</div>
""", unsafe_allow_html=True)

st.info("💡 Buradaki tüm bilgiler, Streamlit Cloud Secrets bölümüne girdiğiniz verilerden okunmaktadır. Değişikliklerin kalıcı olması için sırlarınızı oradan yönetmelisiniz.")

# --- Ayar Görüntüleme Bölümü ---
with st.container(border=True):
    st.subheader("🔗 Mevcut API Ayarları")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<h5>🏪 Shopify Ayarları</h5>", unsafe_allow_html=True)
        st.text_input("Mağaza URL", value=st.session_state.get('shopify_store', 'YOK'), disabled=True)
        st.text_input("Erişim Token'ı", value="********" if st.session_state.get('shopify_token') else 'YOK', type="password", disabled=True)
    
    with col2:
        st.markdown("<h5>🔗 Sentos API Ayarları</h5>", unsafe_allow_html=True)
        st.text_input("Sentos API URL", value=st.session_state.get('sentos_api_url', 'YOK'), disabled=True)
        st.text_input("Sentos API Key", value=st.session_state.get('sentos_api_key', 'YOK'), disabled=True)
        st.text_input("Sentos API Secret", value="********" if st.session_state.get('sentos_api_secret') else 'YOK', type="password", disabled=True)
        st.text_input("Sentos API Cookie", value="********" if st.session_state.get('sentos_cookie') else 'YOK', type="password", disabled=True)

with st.container(border=True):
    st.subheader("📊 Google E-Tablolar Entegrasyonu")
    gcp_json = st.session_state.get('gcp_service_account_json', '')
    if gcp_json:
        try:
            # Sadece client_email'i göstererek anahtarın varlığını teyit edelim
            client_email = json.loads(gcp_json).get('client_email', 'JSON formatı hatalı')
            st.success(f"✅ Google Service Account anahtarı yüklendi. (Hesap: {client_email})")
        except json.JSONDecodeError:
            st.error("❌ Yüklenen Google Service Account anahtarı geçerli bir JSON formatında değil.")
    else:
        st.warning("⚠️ Google Service Account anahtarı Streamlit Secrets'ta bulunamadı.")


st.markdown("---")
st.subheader("🧪 Bağlantı Testleri")
if st.button("🔄 Tüm Bağlantıları Yeniden Test Et", use_container_width=True, type="primary"):
    with st.spinner("Bağlantılar test ediliyor..."):
        # Shopify Testi
        if st.session_state.get('shopify_store') and st.session_state.get('shopify_token'):
            try:
                api = ShopifyAPI(st.session_state.shopify_store, st.session_state.shopify_token)
                result = api.test_connection()
                st.session_state.shopify_status = 'connected'
                st.session_state.shopify_data = result
                st.success(f"✅ Shopify bağlantısı başarılı! ({result.get('name')})")
            except Exception as e:
                st.session_state.shopify_status = 'failed'
                st.error(f"❌ Shopify Bağlantısı kurulamadı: {e}")
        else:
            st.warning("Shopify bilgileri eksik, test edilemedi.")

        # Sentos Testi
        if st.session_state.get('sentos_api_url') and st.session_state.get('sentos_api_key'):
            try:
                api = SentosAPI(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret, st.session_state.sentos_cookie)
                result = api.test_connection()
                if result.get('success'):
                    st.session_state.sentos_status = 'connected'
                    st.session_state.sentos_data = result
                    st.success(f"✅ Sentos bağlantısı başarılı! ({result.get('total_products', 0)} ürün bulundu.)")
                else:
                    raise Exception(result.get('message', 'Bilinmeyen hata'))
            except Exception as e:
                st.session_state.sentos_status = 'failed'
                st.error(f"❌ Sentos Bağlantısı kurulamadı: {e}")
        else:
            st.warning("Sentos bilgileri eksik, test edilemedi.")