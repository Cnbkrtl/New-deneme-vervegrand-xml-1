import streamlit as st
from config_manager import save_all_keys
from shopify_sync import ShopifyAPI, SentosAPI

# Giriş kontrolü
if not st.session_state.get("logged_in"):
    st.error("Please log in to access this page.")
    st.stop()

# --- AYARLAR SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>⚙️ Settings</h1>
    <p>Configure API connections. Settings are encrypted and saved automatically.</p>
</div>
""", unsafe_allow_html=True)

# Test fonksiyonları (değişiklik yok)
def test_shopify_connection(store, token):
    try:
        api = ShopifyAPI(store, token)
        result = api.test_connection()
        st.session_state.shopify_status = 'connected'
        st.session_state.shopify_data = result
        st.success("✅ Shopify connected successfully!")
    except Exception as e:
        st.session_state.shopify_status = 'failed'
        st.error(f"❌ Shopify Connection failed: {e}")

def test_sentos_connection(url, key, secret):
    try:
        api = SentosAPI(url, key, secret)
        result = api.test_connection()
        if result.get('success'):
            st.session_state.sentos_status = 'connected'
            st.session_state.sentos_data = result
            st.success(f"✅ Sentos connected successfully! Found {result.get('total_products', 0)} products.")
        else:
            raise Exception(result.get('message', 'Unknown error'))
    except Exception as e:
        st.session_state.sentos_status = 'failed'
        st.error(f"❌ Sentos Connection failed: {e}")

# --- AYAR FORMU ---
# Formun tamamı yeniden düzenlendi
with st.form("settings_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏪 Shopify Settings")
        shopify_store = st.text_input(
            "Store URL", 
            value=st.session_state.get('shopify_store', ''),
            placeholder="your-store.myshopify.com"
        )
        shopify_token = st.text_input(
            "Access Token", 
            value=st.session_state.get('shopify_token', ''),
            type="password"
        )
    
    with col2:
        st.subheader("Sentos API Settings")
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
    submitted = st.form_submit_button("💾 Save & Test Connections", use_container_width=True, type="primary")

    if submitted:
        # 1. Ayarları Kaydet
        if save_all_keys(
            shopify_store=shopify_store,
            shopify_token=shopify_token,
            sentos_api_url=sentos_api_url,
            sentos_api_key=sentos_api_key,
            sentos_api_secret=sentos_api_secret,
            sentos_cookie=sentos_cookie
        ):
            st.success("✅ All settings saved and encrypted!")
            
            # 2. Session state'i yeni değerlerle güncelle
            st.session_state.shopify_store = shopify_store
            st.session_state.shopify_token = shopify_token
            st.session_state.sentos_api_url = sentos_api_url
            st.session_state.sentos_api_key = sentos_api_key
            st.session_state.sentos_api_secret = sentos_api_secret
            st.session_state.sentos_cookie = sentos_cookie
            
            # 3. Yeni bilgilerle bağlantıları otomatik olarak yeniden test et
            st.info("Re-testing connections with new settings...")
            
            # İki ayrı spinner bloğu oluşturarak testlerin ayrı ayrı çalışmasını sağla
            with st.spinner("Testing Shopify connection..."):
                if shopify_store and shopify_token:
                    test_shopify_connection(shopify_store, shopify_token)
                else:
                    st.warning("Shopify settings are missing.")
                    st.session_state.shopify_status = 'pending'

            with st.spinner("Testing Sentos connection..."):
                if sentos_api_url and sentos_api_key and sentos_api_secret:
                    test_sentos_connection(sentos_api_url, sentos_api_key, sentos_api_secret)
                else:
                    st.warning("Sentos settings are missing.")
                    st.session_state.sentos_status = 'pending'
        else:
            st.error("❌ Failed to save settings.")

# Eski test butonları kaldırıldı. Artık tek bir yerden kontrol ediliyor.