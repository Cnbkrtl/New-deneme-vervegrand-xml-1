import streamlit as st
from config_manager import save_user_keys # save_all_keys yerine save_user_keys
from shopify_sync import ShopifyAPI, SentosAPI
import os # Ortam değişkenlerini okumak için eklendi

# Giriş kontrolü
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- AYARLAR SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>⚙️ Settings</h1>
    <p>Configure API connections. Settings are saved automatically for your user.</p>
</div>
""", unsafe_allow_html=True)

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
with st.form("settings_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏪 Shopify Settings")
        # GÜNCELLEME: Değerler önce ortam değişkeninden (os.getenv) okunur.
        shopify_store = st.text_input(
            "Store URL", 
            value=os.getenv("SHOPIFY_STORE", st.session_state.get('shopify_store', '')),
            placeholder="your-store.myshopify.com"
        )
        shopify_token = st.text_input(
            "Access Token", 
            value=os.getenv("SHOPIFY_TOKEN", st.session_state.get('shopify_token', '')),
            type="password"
        )
    
    with col2:
        st.subheader("Sentos API Settings")
        sentos_api_url = st.text_input(
            "Sentos API URL", 
            value=os.getenv("SENTOS_API_URL", st.session_state.get('sentos_api_url', '')),
            placeholder="https://stildiva.sentos.com.tr/api"
        )
        sentos_api_key = st.text_input(
            "Sentos API Key", 
            value=os.getenv("SENTOS_API_KEY", st.session_state.get('sentos_api_key', ''))
        )
        sentos_api_secret = st.text_input(
            "Sentos API Secret", 
            value=os.getenv("SENTOS_API_SECRET", st.session_state.get('sentos_api_secret', '')),
            type="password"
        )
        sentos_cookie = st.text_input(
            "Sentos API Cookie",
            value=os.getenv("SENTOS_COOKIE", st.session_state.get('sentos_cookie', '')),
            type="password"
        )

    st.markdown("---")
    submitted = st.form_submit_button("💾 Save & Test Connections", use_container_width=True, type="primary")

    if submitted:
        current_username = st.session_state.get("username")
        if save_user_keys(
            username=current_username,
            shopify_store=shopify_store,
            shopify_token=shopify_token,
            sentos_api_url=sentos_api_url,
            sentos_api_key=sentos_api_key,
            sentos_api_secret=sentos_api_secret,
            sentos_cookie=sentos_cookie
        ):
            st.success("✅ Settings saved for user!")
            
            # Session state'i yeni değerlerle güncelle
            st.session_state.update({
                'shopify_store': shopify_store, 'shopify_token': shopify_token,
                'sentos_api_url': sentos_api_url, 'sentos_api_key': sentos_api_key,
                'sentos_api_secret': sentos_api_secret, 'sentos_cookie': sentos_cookie
            })
            
            st.info("Re-testing connections...")
            if shopify_store and shopify_token:
                test_shopify_connection(shopify_store, shopify_token)
            if sentos_api_url and sentos_api_key and sentos_api_secret:
                test_sentos_connection(sentos_api_url, sentos_api_key, sentos_api_secret)
        else:
            st.error("❌ Failed to save settings.")