# pages/1_dashboard.py

import streamlit as st

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("style.css dosyası bulunamadı. Lütfen ana dizine ekleyin.")

# --- Giriş Kontrolü ve Sayfa Kurulumu ---
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

load_css()

# --- DASHBOARD SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>🏠 Dashboard</h1>
    <p>Sentos ve Shopify API Entegrasyon Paneli - Sistem Genel Bakışı</p>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="status-card">', unsafe_allow_html=True)
    shopify_status = st.session_state.get('shopify_status', 'pending')
    shopify_data = st.session_state.get('shopify_data', {})
    
    status_class = 'status-connected' if shopify_status == 'connected' else 'status-failed' if shopify_status == 'failed' else 'status-pending'
    status_icon = '✅' if shopify_status == 'connected' else '❌' if shopify_status == 'failed' else '⏳'
    status_text = f"{status_icon} {shopify_status.capitalize()}"

    st.markdown(f"""
        <div class="card-header">
            <h3>🏪 Shopify Durumu</h3>
            <span class="status-indicator {status_class}">{status_text}</span>
        </div>
        """, unsafe_allow_html=True)

    if shopify_status == 'connected':
        c1, c2 = st.columns(2)
        c1.metric("Ürün Sayısı", shopify_data.get('products_count', 0))
        c2.metric("Para Birimi", shopify_data.get('currency', 'N/A'))
        st.info(f"**Mağaza:** {shopify_data.get('name', 'N/A')} | **Plan:** {shopify_data.get('plan', 'N/A')}")
    else:
        st.warning("Bağlantı kurulamadı. Lütfen Ayarlar sayfasını kontrol edin.")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="status-card">', unsafe_allow_html=True)
    sentos_status = st.session_state.get('sentos_status', 'pending')
    sentos_data = st.session_state.get('sentos_data', {})
    
    status_class = 'status-connected' if sentos_status == 'connected' else 'status-failed' if sentos_status == 'failed' else 'status-pending'
    status_icon = '✅' if sentos_status == 'connected' else '❌' if sentos_status == 'failed' else '⏳'
    status_text = f"{status_icon} {sentos_status.capitalize()}"

    st.markdown(f"""
        <div class="card-header">
            <h3>🔗 Sentos API Durumu</h3>
            <span class="status-indicator {status_class}">{status_text}</span>
        </div>
        """, unsafe_allow_html=True)

    if sentos_status == 'connected':
        st.metric("Sentos'taki Ürün Sayısı", sentos_data.get('total_products', 0))
        st.info(f"**Bağlantı Durumu:** {sentos_data.get('message', 'OK')}")
    else:
        st.warning("Bağlantı kurulamadı. Lütfen Ayarlar sayfasını kontrol edin.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.subheader("⚡ Hızlı İşlemler")
st.info("İşlem yapmak için lütfen kenar çubuğundaki menüyü kullanın.")