import streamlit as st

# ...existing code...

# Aktif sync durumunu göster
if st.session_state.get('sync_status') == "running":
    st.info(f"🔄 Aktif senkronizasyon devam ediyor... Progress: {st.session_state.get('sync_progress', 0)}%")
    
    # Auto-refresh için
    if st.button("🔄 Durumu Yenile"):
        st.rerun()
    
    # Auto-refresh timer
    import time
    time.sleep(2)
    st.rerun()

# ...existing code...