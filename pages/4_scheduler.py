import streamlit as st
import redis
import json
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="Zamanlayıcı Yönetimi", page_icon="⏰")

def get_redis_connection():
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    return redis.from_url(redis_url)

def save_scheduled_jobs(jobs):
    """Zamanlanmış job'ları Redis'e kaydet"""
    try:
        r = get_redis_connection()
        r.set('scheduled_sync_jobs', json.dumps(jobs))
        return True
    except Exception as e:
        st.error(f"Kaydetme hatası: {e}")
        return False

def load_scheduled_jobs():
    """Zamanlanmış job'ları Redis'ten yükle"""
    try:
        r = get_redis_connection()
        jobs_json = r.get('scheduled_sync_jobs')
        if jobs_json:
            return json.loads(jobs_json)
        return []
    except Exception as e:
        st.error(f"Yükleme hatası: {e}")
        return []

def main():
    st.title("⏰ Zamanlayıcı Yönetimi")
    st.markdown("Otomatik senkronizasyon zamanlayıcılarını buradan yönetebilirsiniz.")
    
    # Mevcut job'ları yükle
    scheduled_jobs = load_scheduled_jobs()
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📅 Aktif Zamanlayıcılar", "➕ Yeni Zamanlayıcı", "📊 Durum"])
    
    with tab1:
        st.subheader("Aktif Zamanlayıcılar")
        
        if not scheduled_jobs:
            st.info("Henüz zamanlayıcı bulunmuyor.")
        else:
            for i, job in enumerate(scheduled_jobs):
                with st.expander(f"🔄 {job['name']} - {job['sync_mode']}", expanded=False):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**Mağaza:** {job['shopify_store']}")
                        st.write(f"**Mod:** {job['sync_mode']}")
                        st.write(f"**Sıklık:** Her {job['interval_minutes']} dakikada")
                        
                        if last_run := job.get('last_run'):
                            try:
                                last_dt = datetime.fromisoformat(last_run)
                                next_run = last_dt + timedelta(minutes=job['interval_minutes'])
                                st.write(f"**Son Çalışma:** {last_dt.strftime('%d.%m.%Y %H:%M')}")
                                st.write(f"**Sonraki Çalışma:** {next_run.strftime('%d.%m.%Y %H:%M')}")
                            except:
                                st.write("**Son Çalışma:** Henüz çalışmadı")
                    
                    with col2:
                        # Enable/Disable toggle
                        enabled = st.checkbox("Aktif", value=job.get('enabled', True), key=f"enable_{i}")
                        scheduled_jobs[i]['enabled'] = enabled
                    
                    with col3:
                        # Sil butonu
                        if st.button("🗑️ Sil", key=f"delete_{i}"):
                            scheduled_jobs.pop(i)
                            save_scheduled_jobs(scheduled_jobs)
                            st.rerun()
        
        # Değişiklikleri kaydet
        if st.button("💾 Değişiklikleri Kaydet"):
            if save_scheduled_jobs(scheduled_jobs):
                st.success("Zamanlayıcılar güncellendi!")
                st.rerun()
    
    with tab2:
        st.subheader("Yeni Zamanlayıcı Ekle")
        
        with st.form("new_scheduler"):
            name = st.text_input("Zamanlayıcı Adı", placeholder="Örn: Günlük Stok Güncelleme")
            
            col1, col2 = st.columns(2)
            
            with col1:
                shopify_store = st.text_input("Shopify Mağaza", placeholder="ornek.myshopify.com")
                shopify_token = st.text_input("Shopify Token", type="password")
                sentos_api_url = st.text_input("Sentos API URL", placeholder="https://api.sentos.com.tr")
            
            with col2:
                sentos_user_id = st.text_input("Sentos User ID")
                sentos_api_key = st.text_input("Sentos API Key", type="password")
                sentos_cookie = st.text_area("Sentos Cookie (İsteğe bağlı)", height=100)
            
            # Sync mode seçimi
            sync_modes = [
                "Stock & Variants Only",
                "Full Sync (Create & Update All)",
                "Descriptions Only", 
                "Categories (Product Type) Only",
                "Images Only",
                "Images with SEO Alt Text"
            ]
            sync_mode = st.selectbox("Senkronizasyon Modu", sync_modes)
            
            # Sıklık ayarı
            col1, col2 = st.columns(2)
            with col1:
                interval_type = st.selectbox("Sıklık Türü", ["Dakika", "Saat", "Gün"])
            with col2:
                interval_value = st.number_input("Değer", min_value=1, value=120)
            
            # Dakika cinsine çevir
            if interval_type == "Saat":
                interval_minutes = interval_value * 60
            elif interval_type == "Gün":
                interval_minutes = interval_value * 24 * 60
            else:
                interval_minutes = interval_value
            
            # Form submit
            if st.form_submit_button("➕ Zamanlayıcı Ekle"):
                if all([name, shopify_store, shopify_token, sentos_api_url, sentos_user_id, sentos_api_key]):
                    new_job = {
                        'name': name,
                        'shopify_store': shopify_store,
                        'shopify_token': shopify_token,
                        'sentos_api_url': sentos_api_url,
                        'sentos_user_id': sentos_user_id,
                        'sentos_api_key': sentos_api_key,
                        'sentos_cookie': sentos_cookie,
                        'sync_mode': sync_mode,
                        'interval_minutes': interval_minutes,
                        'enabled': True,
                        'created_at': datetime.now().isoformat()
                    }
                    
                    scheduled_jobs.append(new_job)
                    if save_scheduled_jobs(scheduled_jobs):
                        st.success(f"✅ '{name}' zamanlayıcısı eklendi!")
                        st.rerun()
                else:
                    st.error("Lütfen tüm gerekli alanları doldurun!")
    
    with tab3:
        st.subheader("📊 Sistem Durumu")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Toplam Zamanlayıcı", len(scheduled_jobs))
        
        with col2:
            active_count = sum(1 for job in scheduled_jobs if job.get('enabled', True))
            st.metric("Aktif Zamanlayıcı", active_count)
        
        with col3:
            # Son scheduler çalışma zamanı
            try:
                r = get_redis_connection()
                last_check = r.get('last_scheduler_check')
                if last_check:
                    last_dt = datetime.fromisoformat(last_check.decode())
                    st.metric("Son Kontrol", last_dt.strftime('%H:%M'))
                else:
                    st.metric("Son Kontrol", "Henüz yok")
            except:
                st.metric("Son Kontrol", "Bilinmiyor")
        
        # Keep-alive durumu hakkında bilgi
        st.info("""
        **Keep-Alive Servisleri Hakkında:**
        - Keep-alive sadece web servislerini uyanık tutar
        - Worker'lar job çalıştığında otomatik aktif olur
        - Zamanlanmış sync'ler worker'ları tetikler
        - Her 10 dakikada zamanlayıcı kontrol edilir
        """)

if __name__ == "__main__":
    main()
