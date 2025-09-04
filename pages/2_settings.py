import streamlit as st
# GÜNCELLEME: Modülün tamamı import ediliyor
import config_manager 
from shopify_sync import ShopifyAPI, SentosAPI

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

# Test fonksiyonları (değişiklik yok)
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
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏪 Shopify Ayarları")
        shopify_store = st.text_input(
            "Mağaza URL", 
            value=st.session_state.get('shopify_store', ''),
            placeholder="your-store.myshopify.com"
        )
        shopify_token = st.text_input(
            "Erişim Token'ı", 
            value=st.session_state.get('shopify_token', ''),
            type="password"
        )
    
    with col2:
        st.subheader("Sentos API Ayarları")
        sentos_api_url = st.text_input(
            "Sentos API URL", 
            value=st.session_state.get('sentos_api_url', ''),
            placeholder="https://stildiva.sentos.com.tr/api"
        )
        sentos_api_key = st.text_input(
            "Sentos API Key", 
            value=st.session_state.get('sentos_api_key', '')
        )
        sentos_api_secret = st.text_input(
            "Sentos API Secret", 
            value=st.session_state.get('sentos_api_secret', ''),
            type="password"
        )
        sentos_cookie = st.text_input(
            "Sentos API Cookie",
            value=st.session_state.get('sentos_cookie', ''),
            type="password",
            help="Resim sırasını doğru çekmek için Sentos panelinden alınan Cookie değeri."
        )

    st.markdown("---")
    submitted = st.form_submit_button("💾 Kaydet ve Bağlantıları Test Et", use_container_width=True, type="primary")

    if submitted:
        # 1. Ayarları Kaydet
        # GÜNCELLEME: Fonksiyon, import edilen modül üzerinden çağrılıyor
        if config_manager.save_all_keys(
            shopify_store=shopify_store,
            shopify_token=shopify_token,
            sentos_api_url=sentos_api_url,
            sentos_api_key=sentos_api_key,
            sentos_api_secret=sentos_api_secret,
            sentos_cookie=sentos_cookie
        ):
            st.success("✅ Tüm ayarlar kaydedildi ve şifrelendi!")
            
            # 2. Session state'i yeni değerlerle güncelle
            st.session_state.shopify_store = shopify_store
            st.session_state.shopify_token = shopify_token
            st.session_state.sentos_api_url = sentos_api_url
            st.session_state.sentos_api_key = sentos_api_key
            st.session_state.sentos_api_secret = sentos_api_secret
            st.session_state.sentos_cookie = sentos_cookie
            
            # 3. Yeni bilgilerle bağlantıları otomatik olarak yeniden test et
            st.info("Yeni ayarlarla bağlantılar yeniden test ediliyor...")
            
            with st.spinner("Shopify bağlantısı test ediliyor..."):
                if shopify_store and shopify_token:
                    test_shopify_connection(shopify_store, shopify_token)
                else:
                    st.warning("Shopify ayarları eksik.")
                    st.session_state.shopify_status = 'pending'

            with st.spinner("Sentos bağlantısı test ediliyor..."):
                if sentos_api_url and sentos_api_key and sentos_api_secret:
                    test_sentos_connection(sentos_api_url, sentos_api_key, sentos_api_secret, sentos_cookie)
                else:
                    st.warning("Sentos ayarları eksik.")
                    st.session_state.sentos_status = 'pending'
        else:
            st.error("❌ Ayarlar kaydedilemedi.")