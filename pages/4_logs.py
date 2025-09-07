# pages/4_logs.py

import streamlit as st

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# --- Giriş Kontrolü ve Sayfa Kurulumu ---
if not st.session_state.get("authentication_status"):
    st.error("Lütfen bu sayfaya erişmek için giriş yapın.")
    st.stop()

load_css()

# --- LOGS SAYFASI ---
st.markdown("""
<div class="main-header">
    <h1>📝 Loglar ve Raporlar</h1>
    <p>Geçmiş senkronizasyon görevlerinin detaylarını inceleyin.</p>
</div>
""", unsafe_allow_html=True)

st.info("💡 Bu özellik şu anda geliştirme aşamasındadır. Gelecekte, tamamlanan her senkronizasyon görevinin detaylı dökümü burada listelenecektir.")
st.image("https://i.imgur.com/3CGoC2L.png", caption="Yakında Eklenecek Özellikler")