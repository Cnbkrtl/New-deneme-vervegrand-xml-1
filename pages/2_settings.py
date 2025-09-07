import streamlit as st
import config_manager
from shopify_sync import ShopifyAPI, SentosAPI
import json

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("style.css dosyası bulunamadı. Lütfen ana dizine ekleyin.")

# Giriş kontrolü
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

# --- AYARLAR SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>⚙️ Ayarlar</h1>
    <p>API bağlantılarını yapılandırın. Ayarlarınız şifrelenir ve otomatik olarak kaydedilir.</p>
</div>
""", unsafe_allow_html=True)

# Test fonksiyonları
def test_shopify_connection(store, token):
    try:
        api = ShopifyAPI(store, token)
        result = api.test_connection()
        st.session_state.shopify_status = 'connected'
        st.session_state.shopify_data = result
        st.success("✅ Shopify bağlantısı başarılı!")
    except Exception as e:
        st.session_state.shopify_status = 'failed'
        st.error(f"❌ Shopify Bağlantısı kurulamadı: {e}")

def test_sentos_connection(url, key, secret, cookie):
    try:
        api = SentosAPI(url, key, secret, cookie)
        result = api.test_connection()
        if result.get('success'):
            st.session_state.sentos_status = 'connected'
            st.session_state.sentos_data = result
            st.success(f"✅ Sentos bağlantısı başarılı! {result.get('total_products', 0)} ürün bulundu.")
        else:
            raise Exception(result.get('message', 'Bilinmeyen hata'))
    except Exception as e:
        st.session_state.sentos_status = 'failed'
        st.error(f"❌ Sentos Bağlantısı kurulamadı: {e}")

# --- AYAR FORMU ---
with st.form("settings_form"):
    st.subheader("🔗 API Ayarları")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<h5>🏪 Shopify Ayarları</h5>", unsafe_allow_html=True)
        shopify_store = st.text_input("Mağaza URL", value=st.session_state.get('shopify_store', ''), placeholder="your-store.myshopify.com")
        shopify_token = st.text_input("Erişim Token'ı", value=st.session_state.get('shopify_token', ''), type="password")
    
    with col2:
        st.markdown("<h5><img src='https://api.sentos.com.tr/img/favicon.png' width=20> Sentos API Ayarları</h5>", unsafe_allow_html=True)
        sentos_api_url = st.text_input("Sentos API URL", value=st.session_state.get('sentos_api_url', ''), placeholder="https://stildiva.sentos.com.tr/api")
        sentos_api_key = st.text_input("Sentos API Key", value=st.session_state.get('sentos_api_key', ''))
        sentos_api_secret = st.text_input("Sentos API Secret", value=st.session_state.get('sentos_api_secret', ''), type="password")
        sentos_cookie = st.text_input("Sentos API Cookie", value=st.session_state.get('sentos_cookie', ''), type="password", help="Resim sırasını doğru çekmek için Sentos panelinden alınan Cookie değeri.")

    st.markdown("---")
    st.subheader("📊 Google E-Tablolar Entegrasyonu")
    gcp_service_account_json_str = st.text_area(
        "Google Service Account JSON Anahtarı",
        value=st.session_state.get('gcp_service_account_json', ''),
        placeholder="İndirdiğiniz JSON dosyasının içeriğini buraya yapıştırın...",
        height=250,
        help="Google E-Tablolar'a veri yazabilmek için gereken servis hesabı anahtarı."
    )
    
    st.markdown("---")
    submitted = st.form_submit_button("💾 Kaydet ve Bağlantıları Test Et", use_container_width=True, type="primary")

    if submitted:
        # JSON'ı doğrula
        is_json_valid = True
        if gcp_service_account_json_str:
            try:
                json.loads(gcp_service_account_json_str)
            except json.JSONDecodeError:
                st.error("Girdiğiniz Google Service Account anahtarı geçerli bir JSON formatında değil. Lütfen kontrol edin.")
                is_json_valid = False
        
        if is_json_valid:
            current_username = st.session_state.get("username")
            if not current_username:
                st.error("Kullanıcı adı bulunamadı. Lütfen tekrar giriş yapın.")
            elif config_manager.save_user_keys(
                username=current_username,
                shopify_store=shopify_store,
                shopify_token=shopify_token,
                sentos_api_url=sentos_api_url,
                sentos_api_key=sentos_api_key,
                sentos_api_secret=sentos_api_secret,
                sentos_cookie=sentos_cookie,
                gcp_service_account_json=gcp_service_account_json_str
            ):
                st.success("✅ Ayarlarınız kaydedildi ve şifrelendi!")
                
                # Session state'i güncelle
                st.session_state.update({
                    'shopify_store': shopify_store, 'shopify_token': shopify_token,
                    'sentos_api_url': sentos_api_url, 'sentos_api_key': sentos_api_key,
                    'sentos_api_secret': sentos_api_secret, 'sentos_cookie': sentos_cookie,
                    'gcp_service_account_json': gcp_service_account_json_str
                })
                
                # Bağlantıları yeniden test et
                st.info("Yeni ayarlarla bağlantılar yeniden test ediliyor...")
                if shopify_store and shopify_token:
                    test_shopify_connection(shopify_store, shopify_token)
                if sentos_api_url and sentos_api_key and sentos_api_secret:
                    test_sentos_connection(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
            else:
                st.error("❌ Ayarlar kaydedilemedi.")