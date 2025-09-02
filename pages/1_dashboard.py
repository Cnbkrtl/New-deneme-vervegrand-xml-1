import streamlit as st

# Giriş kontrolü (Tüm sayfa dosyalarının başına bunu ekleyin)
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- DASHBOARD SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>🏠 Dashboard</h1>
    <p>Sentos API to Shopify Sync - System Overview</p>
</div>
""", unsafe_allow_html=True)

# Status Overview
col1, col2 = st.columns(2)

with col1:
    shopify_status = st.session_state.get('shopify_status', 'pending')
    shopify_data = st.session_state.get('shopify_data', {})
    
    st.markdown('<div class="status-card">', unsafe_allow_html=True)
    
    # Card Header
    status_class = 'status-connected' if shopify_status == 'connected' else 'status-failed' if shopify_status == 'failed' else 'status-pending'
    status_text = 'Connected' if shopify_status == 'connected' else 'Failed' if shopify_status == 'failed' else 'Pending'
    st.markdown(f"""
        <div class="card-header">
            <h3>🏪 Shopify Status</h3>
            <span class="status-indicator {status_class}" style="margin-left: auto;">{status_text}</span>
        </div>
    """, unsafe_allow_html=True)

    # Card Body
    st.markdown('<div class="card-body">', unsafe_allow_html=True)
    if shopify_status == 'connected':
        st.markdown(f"""
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{shopify_data.get('products_count', 0)}</div>
                    <div class="stat-label">Products</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{shopify_data.get('currency', 'N/A')}</div>
                    <div class="stat-label">Currency</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Connection not established. Check settings.")
    st.markdown('</div>', unsafe_allow_html=True)

    # Card Footer
    st.markdown('<hr style="border-color: #3c3f4b;">', unsafe_allow_html=True)
    st.markdown('<div class="card-footer">', unsafe_allow_html=True)
    if shopify_status == 'connected':
        st.markdown(f"""
            <p><strong>Shop:</strong> {shopify_data.get('name', 'N/A')}</p>
            <p><strong>Domain:</strong> {shopify_data.get('domain', 'N/A')}</p>
            <p><strong>Plan:</strong> {shopify_data.get('plan', 'N/A')}</p>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<p>Please go to the Settings page to configure your Shopify credentials.</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    sentos_status = st.session_state.get('sentos_status', 'pending')
    sentos_data = st.session_state.get('sentos_data', {})
    
    st.markdown('<div class="status-card">', unsafe_allow_html=True)
    
    # Card Header
    status_class = 'status-connected' if sentos_status == 'connected' else 'status-failed' if sentos_status == 'failed' else 'status-pending'
    status_text = 'Connected' if sentos_status == 'connected' else 'Failed' if sentos_status == 'failed' else 'Pending'
    st.markdown(f"""
        <div class="card-header">
            <h3>🔗 Sentos API Status</h3>
            <span class="status-indicator {status_class}" style="margin-left: auto;">{status_text}</span>
        </div>
    """, unsafe_allow_html=True)

    # Card Body
    st.markdown('<div class="card-body">', unsafe_allow_html=True)
    if sentos_status == 'connected':
        st.markdown(f"""
            <div class="stats-grid">
                <div class="stat-item" style="grid-column: 1 / -1;">
                    <div class="stat-number">{sentos_data.get('total_products', 0)}</div>
                    <div class="stat-label">Products Found</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Connection not established. Check settings.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Card Footer
    st.markdown('<hr style="border-color: #3c3f4b;">', unsafe_allow_html=True)
    st.markdown('<div class="card-footer">', unsafe_allow_html=True)
    if sentos_status == 'connected':
        st.markdown(f"<p><strong>Status:</strong> {sentos_data.get('message', 'OK')}</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p>Please go to the Settings page to configure your Sentos API credentials.</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

st.subheader("⚡ Quick Actions")
st.warning("Please use the navigation in the sidebar to switch pages.")
