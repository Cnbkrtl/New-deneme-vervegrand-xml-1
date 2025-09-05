import streamlit as st
import pandas as pd
from datetime import datetime
from log_manager import load_logs

# --- Sayfa Yapılandırması ve Yardımcı Fonksiyonlar ---
st.set_page_config(layout="wide", page_title="Log ve Analatik")

# Giriş kontrolü
if not st.session_state.get("authentication_status"):
    st.error("Please log in to access this page.")
    st.stop()

# --- LOGS SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>📊 Logs & Analytics</h1>
    <p>Review synchronization history and performance analytics</p>
</div>
""", unsafe_allow_html=True)

logs = load_logs()

if not logs:
    st.info("No sync history found.")
else:
    st.subheader("🕒 Recent Sync History")
    
    log_summaries = []
    for log in logs:
        stats = log.get('stats', {})
        summary = {
            "Timestamp": datetime.fromisoformat(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
            "Total": stats.get('total', 0),
            "Created": stats.get('created', 0),
            "Updated": stats.get('updated', 0),
            "Failed": stats.get('failed', 0),
            "Skipped": stats.get('skipped', 0)
        }
        log_summaries.append(summary)
    
    df_summary = pd.DataFrame(log_summaries)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

    st.subheader("🔍 Log Details")
    selected_log_ts = st.selectbox("Select a sync run to view details:", [log['Timestamp'] for log in df_summary.to_dict('records')])
    
    selected_log = next((log for log in logs if datetime.fromisoformat(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S') == selected_log_ts), None)

    if selected_log:
        with st.expander("View Detailed Product Log", expanded=True):
            details = selected_log.get('details', [])
            if details:
                df_details = pd.DataFrame(details)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                st.info("No detailed product logs available for this run.")
