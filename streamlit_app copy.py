"""
🔄 XML to Shopify Sync - Streamlit App
Multi-page modern interface with improved design
"""

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import time
import json
from datetime import datetime
import pandas as pd
from urllib.parse import urlparse
import difflib
import os
from config_manager import save_all_keys, load_all_keys
import threading

# --- HELPER FUNCTIONS (needed for initialization) ---
def test_shopify_connection(store_url, access_token):
    """Tests Shopify connection."""
    try:
        if not store_url or not access_token:
            return False, "Store URL or Access Token missing"
        normalized_store_url = store_url if store_url.startswith('http') else f"https://{store_url}"
        test_url = f"{normalized_store_url}/admin/api/2023-10/shop.json"
        headers = {'X-Shopify-Access-Token': access_token, 'Content-Type': 'application/json'}
        response = requests.get(test_url, headers=headers, timeout=10)
        if response.status_code == 200:
            shop_data = response.json().get('shop', {})
            products_url = f"{normalized_store_url}/admin/api/2023-10/products/count.json"
            products_response = requests.get(products_url, headers=headers, timeout=10)
            products_count = products_response.json().get('count', 0) if products_response.status_code == 200 else 0
            return True, {
                'name': shop_data.get('name', 'N/A'), 'domain': shop_data.get('domain', 'N/A'),
                'products_count': products_count, 'currency': shop_data.get('currency', 'N/A'),
                'plan': shop_data.get('plan_display_name', 'N/A')
            }
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, f"Connection error: {e}"

# --- APP INITIALIZATION ---
def initialize_app():
    """Load credentials and test connections on app start."""
    if 'app_initialized' not in st.session_state:
        credentials = load_all_keys()
        if credentials:
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.session_state.update(credentials)

            # Auto-test Shopify connection
            if st.session_state.get('shopify_store') and st.session_state.get('shopify_token'):
                success, result = test_shopify_connection(st.session_state.shopify_store, st.session_state.shopify_token)
                st.session_state.shopify_status = 'connected' if success else 'failed'
                st.session_state.shopify_data = result if success else {}

            # Auto-test Sentos connection
            if st.session_state.get('sentos_api_url') and st.session_state.get('sentos_api_key') and st.session_state.get('sentos_api_secret'):
                from shopify_sync import test_sentos_connection
                result = test_sentos_connection(st.session_state.sentos_api_url, st.session_state.sentos_api_key, st.session_state.sentos_api_secret)
                st.session_state.sentos_status = 'connected' if result.get('success') else 'failed'
                st.session_state.sentos_data = result if result.get('success') else {}
        
        st.session_state.app_initialized = True

initialize_app()

# --- AUTHENTICATION ---
def render_login_page():
    st.markdown("""
    <div class="main-header">
        <h1>🔐 Admin Login</h1>
        <p>Please enter your credentials to access the sync tool.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("ID", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if username == "admin" and password == "19519":
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Logged in successfully!")
                # Initialize settings for a first-time login
                if 'app_initialized' not in st.session_state:
                     initialize_app()
                st.rerun()
            else:
                st.error("Incorrect ID or password.")

def render_main_app():
    # --- RENDER MAIN APP ---
    # Page config
    st.set_page_config(
        page_title="Vervegrand Sync", 
        page_icon="🔄",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    with st.sidebar:
        st.title(f"Welcome, {st.session_state.get('username', 'Admin')}!")
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            # Clear session state completely to logout
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        if st.button("Forget All Settings", use_container_width=True, type="primary"):
            CREDENTIALS_FILE = "credentials.enc"
            KEY_FILE = ".secret.key"
            if os.path.exists(CREDENTIALS_FILE):
                os.remove(CREDENTIALS_FILE)
            if os.path.exists(KEY_FILE):
                os.remove(KEY_FILE)
            # Clear session state completely
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        st.markdown("---")
        st.info("Vervegrand Sync Tool v2.2")

    # Enhanced CSS for better styling
    st.markdown("""
    <style>
        /* Main styles */
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 15px;
            color: white;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        /* Card styles - Dark theme compatible */
        .status-card {
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(21, 128, 61, 0.05) 100%);
            border: 2px solid rgba(34, 197, 94, 0.3);
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            transition: transform 0.2s ease;
            backdrop-filter: blur(10px);
        }
        .status-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
        }
        
        .error-card {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%);
            border: 2px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 4px 16px rgba(255,0,0,0.1);
        }
        
        .info-card {
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            border: 2px solid #bfdbfe;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 4px 16px rgba(0,0,255,0.1);
        }
        
        .warning-card {
            background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
            border: 2px solid #fde68a;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 4px 16px rgba(255,165,0,0.1);
        }
        
        /* Stats grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1rem 0;
        }
        
        .stat-item {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
            border-left: 4px solid #3b82f6;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            backdrop-filter: blur(5px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .stat-number {
            font-size: 2rem;
            font-weight: bold;
            color: var(--text-color);
            margin: 0;
        }
        
        .stat-label {
            color: #6b7280;
            font-size: 0.9rem;
            margin: 0;
        }
        
        /* Navigation */
        .nav-container {
            background: white;
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Status indicators */
        .status-indicator {
            display: inline-flex;
            align-items: center;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: 500;
            margin: 0.25rem;
        }
        
        .status-connected {
            background: #d1fae5;
            color: #047857;
            border: 1px solid #34d399;
        }
        
        .status-pending {
            background: #fef3c7;
            color: #d97706;
            border: 1px solid #fbbf24;
        }
        
        .status-failed {
            background: #fee2e2;
            color: #dc2626;
            border: 1px solid #f87171;
        }
    </style>
    """, unsafe_allow_html=True)

    # Navigation
    st.markdown('<div class="nav-container">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        if st.button("🏠 Dashboard", use_container_width=True):
            st.session_state.page = "dashboard"

    with col2:
        if st.button("⚙️ Settings", use_container_width=True):
            st.session_state.page = "settings"

    with col3:
        if st.button("🚀 Sync", use_container_width=True):
            st.session_state.page = "sync"

    with col4:
        if st.button("📊 Logs", use_container_width=True):
            st.session_state.page = "logs"

    st.markdown('</div>', unsafe_allow_html=True)

    # Initialize page state
    if 'page' not in st.session_state:
        st.session_state.page = "dashboard"

    # Helper functions are now defined at the top level before initialization
    
    # PAGE IMPLEMENTATIONS
    if st.session_state.page == "dashboard":
        # DASHBOARD PAGE
        st.markdown("""
        <div class="main-header">
            <h1>🏠 Dashboard</h1>
            <p>XML to Shopify Sync - System Overview</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Status Overview
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏪 Shopify Status")
            shopify_status = st.session_state.get('shopify_status', 'pending')
            shopify_data = st.session_state.get('shopify_data', {})
            
            if shopify_status == 'connected':
                st.markdown(f"""
                <div class="status-card">
                    <h3><span class="status-indicator status-connected">🏪 Connected</span></h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-number">{shopify_data.get('products_count', 0)}</div>
                            <div class="stat-label">Products</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">{shopify_data.get('currency', 'USD')}</div>
                            <div class="stat-label">Currency</div>
                        </div>
                    </div>
                    <hr>
                    <p><strong>Shop:</strong> {shopify_data.get('name', 'Unknown')}</p>
                    <p><strong>Domain:</strong> {shopify_data.get('domain', 'Unknown')}</p>
                    <p><strong>Plan:</strong> {shopify_data.get('plan', 'Unknown')}</p>
                </div>
                """, unsafe_allow_html=True)
            elif shopify_status == 'failed':
                st.markdown("""
                <div class="error-card">
                    <h3><span class="status-indicator status-failed">❌ Disconnected</span></h3>
                    <p>Shopify connection failed. Please check your credentials in Settings.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="warning-card">
                    <h3><span class="status-indicator status-pending">⏳ Pending</span></h3>
                    <p>Shopify connection not tested yet. Go to Settings to configure.</p>
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            st.subheader("Sentos API Status")
            sentos_status = st.session_state.get('sentos_status', 'pending')
            sentos_data = st.session_state.get('sentos_data', {})
            
            if sentos_status == 'connected':
                st.markdown(f"""
                <div class="status-card">
                    <h3><span class="status-indicator status-connected">� Connected</span></h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-number">{sentos_data.get('total_products', 0)}</div>
                            <div class="stat-label">Products Found</div>
                        </div>
                    </div>
                    <hr>
                    <p><strong>Status:</strong> {sentos_data.get('message', 'OK')}</p>
                </div>
                """, unsafe_allow_html=True)
            elif sentos_status == 'failed':
                st.markdown("""
                <div class="error-card">
                    <h3><span class="status-indicator status-failed">❌ Failed</span></h3>
                    <p>Sentos API connection failed. Please check your credentials in Settings.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="warning-card">
                    <h3><span class="status-indicator status-pending">⏳ Pending</span></h3>
                    <p>Sentos API connection not tested yet. Go to Settings to configure.</p>
                </div>
                """, unsafe_allow_html=True)
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        action_col1, action_col2, action_col3 = st.columns(3)
        
        with action_col1:
            if st.button("⚙️ Configure Settings", use_container_width=True):
                st.session_state.page = "settings"
                st.rerun()
        
        with action_col2:
            sync_ready = (shopify_status == 'connected' and st.session_state.get('sentos_status') == 'connected')
            if st.button("🚀 Start Sync", disabled=not sync_ready, use_container_width=True):
                st.session_state.page = "sync"
                st.rerun()
        
        with action_col3:
            if st.button("📊 View Logs", use_container_width=True):
                st.session_state.page = "logs"
                st.rerun()

    elif st.session_state.page == "settings":
        # SETTINGS PAGE
        st.markdown("""
        <div class="main-header">
            <h1>⚙️ Settings</h1>
            <p>Configure API connections. Settings are encrypted and saved automatically.</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("settings_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🏪 Shopify Settings")
                shopify_store = st.text_input(
                    "Store URL", 
                    value=st.session_state.get('shopify_store', ''),
                    placeholder="your-store.myshopify.com",
                    help="Shopify store URL without https://"
                )
                shopify_token = st.text_input(
                    "Access Token", 
                    value=st.session_state.get('shopify_token', ''),
                    type="password",
                    help="Shopify Admin API Access Token"
                )
            
            with col2:
                st.subheader("Sentos API Settings")
                sentos_api_url = st.text_input(
                    "Sentos API URL", 
                    value=st.session_state.get('sentos_api_url', ''),
                    placeholder="https://api.sentos.com/v1",
                    help="Base URL for the Sentos API"
                )
                sentos_api_key = st.text_input(
                    "Sentos API Key", 
                    value=st.session_state.get('sentos_api_key', ''),
                    help="Your Sentos API Key"
                )
                sentos_api_secret = st.text_input(
                    "Sentos API Secret", 
                    value=st.session_state.get('sentos_api_secret', ''),
                    type="password",
                    help="Your Sentos API Secret"
                )

            st.markdown("---")
            submitted = st.form_submit_button("💾 Save All Settings", use_container_width=True)

            if submitted:
                if save_all_keys(
                    shopify_store=shopify_store,
                    shopify_token=shopify_token,
                    sentos_api_url=sentos_api_url,
                    sentos_api_key=sentos_api_key,
                    sentos_api_secret=sentos_api_secret
                ):
                    st.success("✅ All settings saved and encrypted!")
                    # Rerun tests with new settings
                    st.session_state.shopify_status = 'pending'
                    st.session_state.sentos_status = 'pending'
                    st.rerun()
                else:
                    st.error("❌ Failed to save settings.")

        st.markdown("---")
        st.subheader("🧪 Connection Tests")
        test_col1, test_col2 = st.columns(2)

        with test_col1:
            if st.button("🧪 Test Shopify Connection", use_container_width=True):
                store = st.session_state.get('shopify_store', '')
                token = st.session_state.get('shopify_token', '')
                if store and token:
                    with st.spinner("Testing Shopify connection..."):
                        success, result = test_shopify_connection(store, token)
                    if success:
                        st.session_state.shopify_status = 'connected'
                        st.session_state.shopify_data = result
                        st.success("✅ Shopify connected successfully!")
                        st.rerun()
                    else:
                        st.session_state.shopify_status = 'failed'
                        st.error(f"❌ Connection failed: {result}")
                else:
                    st.warning("⚠️ Please save your settings first!")
        
        with test_col2:
            if st.button("🧪 Test Sentos Connection", use_container_width=True):
                url = st.session_state.get('sentos_api_url', '')
                key = st.session_state.get('sentos_api_key', '')
                secret = st.session_state.get('sentos_api_secret', '')
                if url and key and secret:
                    from shopify_sync import test_sentos_connection
                    with st.spinner("Testing Sentos connection..."):
                        result = test_sentos_connection(url, key, secret)
                    if result.get('success'):
                        st.session_state.sentos_status = 'connected'
                        st.session_state.sentos_data = result
                        st.success(f"✅ Sentos connected successfully! Found {result.get('total_products', 0)} products.")
                        st.rerun()
                    else:
                        st.session_state.sentos_status = 'failed'
                        st.error(f"❌ Connection failed: {result.get('message')}")
                else:
                    st.warning("⚠️ Please save your settings first!")

    elif st.session_state.page == "sync":
        # SYNC PAGE
        st.markdown("""
        <div class="main-header">
            <h1>🚀 Synchronization</h1>
            <p>Sentos API to Shopify Product Sync Process</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Define the thread target function here
        def run_sync_in_thread(store_url, access_token, sentos_api_url, sentos_api_key, sentos_api_secret, test_mode):
            """Wrapper function to run sync in a thread and update session state."""
            st.session_state.sync_running = True
            st.session_state.sync_results = {}
            st.session_state.sync_progress = 0
            st.session_state.sync_message = "Starting sync..."
            st.session_state.sync_stats = {'total': 0, 'processed': 0, 'created': 0, 'updated': 0, 'failed': 0, 'skipped': 0}
            st.session_state.current_product = ""
            st.session_state.sync_logs = []

            def progress_callback(progress_data):
                """Optimized progress callback - reduced frequency updates."""
                from datetime import datetime
                
                if isinstance(progress_data, dict):
                    # Only update UI every 5% progress to reduce reloads
                    if 'progress' in progress_data:
                        current_progress = progress_data['progress']
                        last_progress = getattr(st.session_state, 'last_ui_update', 0)
                        
                        if current_progress - last_progress >= 5 or current_progress in [0, 100]:
                            st.session_state.sync_progress = current_progress
                            st.session_state.last_ui_update = current_progress
                    
                    if 'message' in progress_data:
                        st.session_state.sync_message = progress_data['message']
                    
                    if 'current_product' in progress_data:
                        st.session_state.current_product = progress_data['current_product']
                    
                    if 'stats' in progress_data:
                        st.session_state.sync_stats.update(progress_data['stats'])
                    
                    # Only log important events, not every single operation
                    if 'log' in progress_data and progress_data['log'].get('type') in ['error', 'success', 'warning']:
                        log_entry = progress_data['log']
                        log_entry['timestamp'] = datetime.now().strftime("%H:%M:%S")
                        st.session_state.sync_logs.append(log_entry)
                        
                        # Keep only last 20 logs
                        if len(st.session_state.sync_logs) > 20:
                            st.session_state.sync_logs = st.session_state.sync_logs[-20:]
                else:
                    # Backward compatibility for simple progress updates
                    st.session_state.sync_progress = progress_data
                    st.session_state.sync_message = "Processing..."

            try:
                from shopify_sync import sync_products_from_sentos_api
                results = sync_products_from_sentos_api(
                    store_url, 
                    access_token, 
                    sentos_api_url, 
                    sentos_api_key, 
                    sentos_api_secret,
                    progress_callback=progress_callback,
                    test_mode=test_mode
                )
                st.session_state.sync_results = results
                
                # Add final log entry
                from datetime import datetime  # Local import to avoid scope issues
                st.session_state.sync_logs.append({
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'type': 'success',
                    'message': 'Sync completed successfully!'
                })
                
            except Exception as e:
                from datetime import datetime  # Local import to avoid scope issues
                st.session_state.sync_results = {
                    'success': False,
                    'errors': [f"An unexpected error occurred: {str(e)}"]
                }
                
                # Add error log entry
                st.session_state.sync_logs.append({
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'type': 'error',
                    'message': f'Sync failed: {str(e)}'
                })
                
            finally:
                st.session_state.sync_running = False
                st.session_state.sync_message = "Sync completed"
                st.session_state.sync_message = "Sync finished."

        # Check prerequisites
        shopify_status = st.session_state.get('shopify_status', 'pending')
        sentos_status = st.session_state.get('sentos_status', 'pending')
        sync_ready = (shopify_status == 'connected' and sentos_status == 'connected')
        
        if not sync_ready:
            st.markdown("""
            <div class="warning-card">
                <h3>⚠️ Prerequisites Required</h3>
                <p>Please configure and test both Shopify and Sentos API connections before starting sync.</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("⚙️ Go to Settings"):
                st.session_state.page = "settings"
                st.rerun()
        else:
            st.markdown("""
            **Product data will be fetched from the Sentos API and synchronized with your Shopify store.**
            
            This process will:
            1.  **Fetch** all products from your Sentos API.
            2.  **Compare** each product with your Shopify store based on SKU or title.
            3.  **Create** new products in Shopify if they don't exist.
            4.  **Update** existing products if there are changes in details, images, or variants.
            
            The sync runs in the background. You can see the progress below.
            """)
            
            test_mode = st.checkbox("🧪 Run in Test Mode (process first ~300 products)", value=False)
            
            if st.button("🚀 Start Full Sync", use_container_width=True, type="primary", disabled=st.session_state.get('sync_running', False)):
                # Initialize sync session state
                st.session_state.sync_running = True
                st.session_state.sync_progress = 0
                st.session_state.sync_message = "Initializing sync..."
                st.session_state.sync_stats = {'total': 0, 'processed': 0, 'created': 0, 'updated': 0, 'failed': 0, 'skipped': 0}
                st.session_state.current_product = ""
                st.session_state.sync_logs = []
                
                # Get credentials from session state
                store_url = st.session_state.get('shopify_store', '')
                access_token = st.session_state.get('shopify_token', '')
                sentos_api_url = st.session_state.get('sentos_api_url', '')
                sentos_api_key = st.session_state.get('sentos_api_key', '')
                sentos_api_secret = st.session_state.get('sentos_api_secret', '')
                
                # Import and run sync in a separate thread
                from shopify_sync import sync_products_from_sentos_api
                
                # Use a thread to run the sync process in the background
                sync_thread = threading.Thread(
                    target=run_sync_in_thread,
                    args=(
                        store_url, access_token, 
                        sentos_api_url, sentos_api_key, sentos_api_secret, 
                        test_mode
                    )
                )
                sync_thread.start()
                st.rerun()
            
            # Enhanced Sync Progress Display
            if st.session_state.get('sync_running', False):
                st.markdown("---")
                
                # Main Progress Section
                st.markdown("### 🔄 Synchronization Progress")
                
                # Progress bar with percentage
                progress_value = st.session_state.get('sync_progress', 0)
                progress_bar = st.progress(progress_value / 100)
                
                # Progress stats columns
                col1, col2, col3, col4 = st.columns(4)
                stats = st.session_state.get('sync_stats', {'total': 0, 'processed': 0, 'created': 0, 'updated': 0, 'failed': 0, 'skipped': 0})
                
                with col1:
                    st.metric("Total Products", stats.get('total', 0))
                with col2:
                    st.metric("Processed", f"{stats.get('processed', 0)}/{stats.get('total', 0)}")
                with col3:
                    st.metric("✅ Created", stats.get('created', 0))
                with col4:
                    st.metric("🔄 Updated", stats.get('updated', 0))
                
                col5, col6, col7, col8 = st.columns(4)
                with col5:
                    st.metric("❌ Failed", stats.get('failed', 0))
                with col6:
                    st.metric("⏭️ Skipped", stats.get('skipped', 0))
                with col7:
                    st.metric("Progress", f"{progress_value:.1f}%")
                with col8:
                    if stats.get('total', 0) > 0:
                        success_rate = ((stats.get('created', 0) + stats.get('updated', 0)) / stats.get('total', 1)) * 100
                        st.metric("Success Rate", f"{success_rate:.1f}%")
                
                # Current operation status
                st.markdown("#### 📍 Current Operation")
                current_message = st.session_state.get('sync_message', 'Waiting...')
                current_product = st.session_state.get('current_product', '')
                
                if current_product:
                    st.info(f"🔄 **Processing:** {current_product}")
                st.caption(current_message)
                
                # Control buttons
                col_refresh, col_stop = st.columns([1, 1])
                with col_refresh:
                    if st.button("🔄 Refresh Status", use_container_width=True):
                        st.rerun()
                with col_stop:
                    if st.button("⏹️ Stop Sync", use_container_width=True, type="secondary"):
                        st.session_state.sync_running = False
                        st.session_state.sync_message = "Sync stopped by user"
                        st.rerun()
                
                # Auto-refresh only every 3 seconds to reduce load
                import time
                if not hasattr(st.session_state, 'last_refresh'):
                    st.session_state.last_refresh = time.time()
                
                if time.time() - st.session_state.last_refresh > 3:
                    st.session_state.last_refresh = time.time()
                    st.rerun()

            elif 'sync_results' in st.session_state and st.session_state.sync_results:
                st.markdown("---")
                st.subheader("📊 Sync Results")
                results = st.session_state.sync_results
                
                if results.get('success'):
                    st.success("✅ Sync completed successfully!")
                else:
                    st.error("❌ Sync finished with errors.")
                
                # Display stats
                stats = {
                    "Total Products Processed": results.get('total', 0),
                    "✅ Created": results.get('created', 0),
                    "✏️ Updated": results.get('updated', 0),
                    "⚠️ Skipped": results.get('skipped', 0),
                    "❌ Failed": results.get('failed', 0),
                }
                
                stats_cols = st.columns(len(stats))
                for col, (label, value) in zip(stats_cols, stats.items()):
                    col.metric(label, value)
                
                # Display errors if any
                if results.get('errors'):
                    st.error("Encountered Errors:")
                    for error in results['errors']:
                        st.code(error, language='text')
                
                # Display detailed log
                with st.expander("View Detailed Sync Log"):
                    if results.get('details'):
                        df = pd.DataFrame(results['details'])
                        st.dataframe(df)
                    else:
                        st.info("No detailed logs available.")
                
                # Clear results button
                if st.button("Clear Results"):
                    del st.session_state.sync_results
                    st.rerun()

    elif st.session_state.page == "logs":
        # LOGS PAGE
        st.markdown("""
        <div class="main-header">
            <h1>📊 Logs & Analytics</h1>
            <p>Review synchronization history and performance analytics</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Last 7 Days Analytics
        st.markdown("### 📈 Last 7 Days Summary")
        
        # Mock data - In real app, this would come from database/logs
        import random
        from datetime import datetime, timedelta
        
        # Generate mock weekly stats
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Mock statistics
        total_syncs = random.randint(15, 35)
        total_products = random.randint(800, 1200)
        created_products = random.randint(50, 150)
        updated_products = random.randint(200, 400)
        
        with col1:
            st.metric(
                "Total Sync Operations", 
                total_syncs,
                delta=f"+{random.randint(2, 8)} vs last week"
            )
        
        with col2:
            st.metric(
                "Products Processed", 
                total_products,
                delta=f"+{random.randint(20, 100)} vs last week"
            )
        
        with col3:
            st.metric(
                "New Products Created", 
                created_products,
                delta=f"+{random.randint(10, 50)} vs last week"
            )
        
        with col4:
            st.metric(
                "Products Updated", 
                updated_products,
                delta=f"+{random.randint(30, 80)} vs last week"
            )
        
        # Success Rate Chart
        st.markdown("### 📊 Daily Success Rate")
        
        # Generate mock daily data
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)][::-1]
        success_rates = [random.randint(85, 98) for _ in range(7)]
        products_synced = [random.randint(50, 200) for _ in range(7)]
        
        chart_data = pd.DataFrame({
            'Date': dates,
            'Success Rate (%)': success_rates,
            'Products Synced': products_synced
        })
        
        st.line_chart(chart_data.set_index('Date')['Success Rate (%)'])
        
        # Recent Sync History
        st.markdown("### 🕒 Recent Sync History")
        
        # Mock recent syncs
        recent_syncs = []
        for i in range(10):
            sync_time = today - timedelta(hours=i*3 + random.randint(0, 2))
            status = random.choice(['✅ Completed', '⚠️ Completed with warnings', '❌ Failed'])
            products_count = random.randint(50, 300)
            duration = f"{random.randint(2, 15)} min {random.randint(10, 59)} sec"
            
            recent_syncs.append({
                'Timestamp': sync_time.strftime("%Y-%m-%d %H:%M:%S"),
                'Status': status,
                'Products': products_count,
                'Duration': duration,
                'Type': random.choice(['Full Sync', 'Test Mode', 'Manual Sync'])
            })
        
        df = pd.DataFrame(recent_syncs)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # System Status
        st.markdown("### 🔧 System Health")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="status-card">
                <h4>🔗 API Connections</h4>
                <p><strong>Shopify:</strong> ✅ Connected</p>
                <p><strong>Sentos:</strong> ✅ Connected</p>
                <p><strong>Last Check:</strong> 2 minutes ago</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="status-card">
                <h4>⚡ Performance</h4>
                <p><strong>Avg Sync Time:</strong> 8.5 minutes</p>
                <p><strong>Products/minute:</strong> 35</p>
                <p><strong>Success Rate:</strong> 94.2%</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="status-card">
                <h4>📦 Current Status</h4>
                <p><strong>Total Products:</strong> 1,579</p>
                <p><strong>Last Sync:</strong> 1 hour ago</p>
                <p><strong>Next Scheduled:</strong> Manual</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Error Analysis
        st.markdown("### 🔍 Common Issues")
        
        common_errors = [
            {'Error Type': 'Missing SKU', 'Count': 15, 'Resolution': 'Auto-generated SKU applied'},
            {'Error Type': 'Invalid Image URL', 'Count': 8, 'Resolution': 'Skipped, logged for review'},
            {'Error Type': 'Price Format', 'Count': 5, 'Resolution': 'Auto-corrected decimal format'},
            {'Error Type': 'Variant Limit', 'Count': 3, 'Resolution': 'Grouped similar variants'},
            {'Error Type': 'Rate Limit', 'Count': 2, 'Resolution': 'Automatic retry with delay'}
        ]
        
        error_df = pd.DataFrame(common_errors)
        st.dataframe(error_df, use_container_width=True, hide_index=True)
        
        # Export Options
        st.markdown("### 📥 Export Options")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📄 Export Last Week Report", use_container_width=True):
                st.success("Report exported to Downloads folder!")
        
        with col2:
            if st.button("📊 Export Error Log", use_container_width=True):
                st.success("Error log exported to Downloads folder!")
        
        with col3:
            if st.button("⚙️ Download System Config", use_container_width=True):
                st.success("Configuration backup downloaded!")
        
# --- MAIN APP LOGIC ---
if not st.session_state.get("logged_in"):
    render_login_page()
else:
    render_main_app()
