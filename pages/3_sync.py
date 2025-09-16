# pages/3_sync.py (Güncellenmiş Sürüm)

import streamlit as st
import threading
import queue
import time
import pandas as pd
from datetime import timedelta

# CSS'i yükle
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# YENİ: Arka plandaki ana senkronizasyon fonksiyonlarını yeni runner dosyasından içe aktarıyoruz.
# sync_runner.py dosyasında, bu sayfanın bozulmaması için orijinal fonksiyon isimleri korunmuştur.
from sync_runner import (
    sync_products_from_sentos_api,
    sync_missing_products_only,
    sync_single_product_by_sku
)

# --- Session State Başlatma ---
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
# ... (Diğer session_state tanımlamaları aynı kalır) ...

# --- Giriş Kontrolü ---
if not st.session_state.get("authentication_status"):
    st.error("Bu sayfaya erişmek için lütfen giriş yapın.")
    st.stop()

# --- (Sayfanın geri kalanı, fonksiyon çağrıları aynı isimlerle yapıldığı için DEĞİŞMEDEN kalabilir) ---
# Örnek olarak, thread başlatma bölümü artık yeni import edilen fonksiyonu doğru şekilde çağıracaktır:
# thread = threading.Thread(
#     target=sync_products_from_sentos_api, # Bu artık sync_runner'dan geliyor.
#     kwargs=thread_kwargs,
#     daemon=True
# )

# --- Tam Kod ---
# (Yukarıdaki import değişikliği dışında dosyanın geri kalan içeriği aynıdır)

# --- Session State Başlatma ---
if 'sync_running' not in st.session_state:
    st.session_state.sync_running = False
if 'sync_thread' not in st.session_state:
    st.session_state.sync_thread = None
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = None
if 'live_log' not in st.session_state:
    st.session_state.live_log = []

if 'sync_missing_running' not in st.session_state:
    st.session_state.sync_missing_running = False
if 'missing_sync_thread' not in st.session_state:
    st.session_state.missing_sync_thread = None
if 'sync_missing_results' not in st.session_state:
    st.session_state.sync_missing_results = None
if 'live_log_missing' not in st.session_state:
    st.session_state.live_log_missing = []

if 'stop_sync_event' not in st.session_state:
    st.session_state.stop_sync_event = threading.Event()
if 'progress_queue' not in st.session_state:
    st.session_state.progress_queue = queue.Queue()


# --- Sayfa Başlığı ---
st.markdown("""
<div class="main-header">
    <h1>🚀 Ürünleri Senkronize Et</h1>
    <p>Sentos ve Shopify arasındaki senkronizasyon görevlerini başlatın, izleyin ve inceleyin.</p>
</div>
""", unsafe_allow_html=True)

# --- Arayüz Mantığı ---
sync_ready = (st.session_state.get('shopify_status') == 'connected' and 
              st.session_state.get('sentos_status') == 'connected')

is_any_sync_running = st.session_state.sync_running or st.session_state.sync_missing_running

# --- Ortak İlerleme ve Sonuç Gösterim Fonksiyonları ---
def display_progress(title, results_key, log_key):
    st.subheader(title)
    if st.button("🛑 Mevcut Görevi Durdur", use_container_width=True, key=f"stop_{results_key}"):
        if st.session_state.stop_sync_event:
            st.session_state.stop_sync_event.set()
            st.warning("Durdurma sinyali gönderildi. Mevcut işlemlerin bitmesi bekleniyor...")

    progress_bar = st.progress(0, text="Başlatılıyor...")
    stats_placeholder = st.empty()
    log_expander = st.expander("Canlı Gelişmeleri Göster", expanded=True)
    with log_expander:
        log_placeholder = st.empty()

    while True:
        try:
            update = st.session_state.progress_queue.get(timeout=1)
            
            if 'progress' in update:
                progress_bar.progress(update['progress'] / 100.0, text=update.get('message', 'İşleniyor...'))
            
            if 'stats' in update:
                stats = update['stats']
                with stats_placeholder.container():
                    cols = st.columns(5)
                    cols[0].metric("Toplam", f"{stats.get('processed', 0)}/{stats.get('total', 0)}")
                    cols[1].metric("✅ Oluşturuldu", stats.get('created', 0))
                    cols[2].metric("🔄 Güncellendi", stats.get('updated', 0))
                    cols[3].metric("❌ Hatalı", stats.get('failed', 0))
                    cols[4].metric("⏭️ Atlandı", stats.get('skipped', 0))

            if 'log_detail' in update:
                st.session_state[log_key].insert(0, update['log_detail'])
                log_html = "".join(st.session_state[log_key][:50])
                log_placeholder.markdown(f'<div style="height:300px;overflow-y:scroll;border:1px solid #333;padding:10px;border-radius:5px;font-family:monospace;">{log_html}</div>', unsafe_allow_html=True)
            
            if update.get('status') in ['done', 'error']:
                if update.get('status') == 'done':
                    st.session_state[results_key] = update.get('results')
                else:
                    st.error(f"Bir hata oluştu: {update.get('message')}")
                    st.session_state[results_key] = {'stats': {}, 'details': [{'status': 'error', 'reason': update.get('message')}]}
                break
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            st.error(f"Arayüz güncelleme döngüsünde hata: {e}")
            break
    
    st.session_state.sync_running = False
    st.session_state.sync_missing_running = False
    st.rerun()

def display_results(title, results):
    st.subheader(title)
    stats = results.get('stats', {})
    duration = results.get('duration', 'N/A')
    
    st.success(f"Görev {duration} sürede tamamlandı. Özet aşağıdadır.")
    
    cols = st.columns(5)
    cols[0].metric("İşlenen Toplam Ürün", f"{stats.get('processed', 0)}/{stats.get('total', 0)}")
    cols[1].metric("✅ Oluşturuldu", stats.get('created', 0))
    cols[2].metric("🔄 Güncellendi", stats.get('updated', 0))
    cols[3].metric("❌ Hatalı", stats.get('failed', 0))
    cols[4].metric("⏭️ Atlandı", stats.get('skipped', 0))

    with st.expander("Detaylı Raporu Görüntüle"):
        details = results.get('details', [])
        if details:
            st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
        else:
            st.info("Bu çalışma için detaylı ürün raporu oluşturulmadı.")

# --- Ana Arayüz Mantığı ---
if not sync_ready and not is_any_sync_running:
    st.warning("⚠️ Lütfen senkronizasyonu başlatmadan önce Ayarlar menüsünden her iki API bağlantısını da yapılandırın ve test edin.")

elif st.session_state.sync_running:
    display_progress("📊 Senkronizasyon Sürüyor...", 'sync_results', 'live_log')
elif st.session_state.sync_missing_running:
    display_progress("📊 Eksik Ürünler Oluşturuluyor...", 'sync_missing_results', 'live_log_missing')

else:
    if st.session_state.sync_results:
        display_results("✅ Senkronizasyon Görevi Tamamlandı", st.session_state.sync_results)
        st.session_state.sync_results = None
    if st.session_state.sync_missing_results:
        display_results("✅ Eksik Ürün Oluşturma Görevi Tamamlandı", st.session_state.sync_missing_results)
        st.session_state.sync_missing_results = None

    st.markdown("---")
    st.subheader("Yeni Bir Genel Senkronizasyon Görevi Başlat")
    
    sync_mode = st.selectbox(
        "Senkronizasyon Tipini Seç", 
        [
            "Tam Senkronizasyon (Tümünü Oluştur ve Güncelle)", 
            "Sadece Stok ve Varyantlar", 
            "Sadece Resimler", 
            "SEO Alt Metinli Resimler", 
            "Sadece Açıklamalar", 
            "Sadece Kategoriler (Ürün Tipi)"
        ], 
        index=0,
        help="Gerçekleştirmek istediğiniz senkronizasyon görevini seçin."
    )
    col1, col2 = st.columns(2)
    test_mode = col1.checkbox("Test Modu (İlk 20 ürünü senkronize et)", value=True, help="Tam bir senkronizasyon çalıştırmadan bağlantıyı ve mantığı test etmek için yalnızca Sentos'taki ilk 20 ürünü işler.")
    max_workers = col2.number_input("Eş Zamanlı Çalışan Sayısı", 1, 50, 2, help="Aynı anda işlenecek ürün sayısı. API limitlerine takılmamak için dikkatli artırın.")

    if st.button("🚀 Genel Senkronizasyonu Başlat", type="primary", use_container_width=True, disabled=not sync_ready):
        st.session_state.sync_running = True
        st.session_state.live_log = []
        st.session_state.stop_sync_event = threading.Event()
        
        thread_kwargs = {
            'store_url': st.session_state.shopify_store, 
            'access_token': st.session_state.shopify_token,
            'sentos_api_url': st.session_state.sentos_api_url, 
            'sentos_api_key': st.session_state.sentos_api_key,
            'sentos_api_secret': st.session_state.sentos_api_secret, 
            'sentos_cookie': st.session_state.sentos_cookie,
            'test_mode': test_mode, 
            'max_workers': max_workers, 
            'sync_mode': sync_mode,
            'progress_callback': st.session_state.progress_queue.put,
            'stop_event': st.session_state.stop_sync_event
        }
        
        thread = threading.Thread(
            target=sync_products_from_sentos_api, 
            kwargs=thread_kwargs, 
            daemon=True
        )
        st.session_state.sync_thread = thread
        thread.start()
        st.rerun()

    st.markdown("---")
    with st.expander("✨ Özellik: Sadece Eksik Ürünleri Oluştur"):
        st.info("Bu araç, Sentos'taki ürünleri Shopify ile karşılaştırır ve yalnızca Shopify'da mevcut olmayan ürünleri oluşturur. Mevcut ürünleri güncellemez.")
        missing_test_mode = st.checkbox("Test Modu (İlk 20 ürünü tara)", value=True, key="missing_test_mode")
        
        if st.button("🚀 Eksik Ürünleri Bul ve Oluştur", use_container_width=True, disabled=not sync_ready):
            st.session_state.sync_missing_running = True
            st.session_state.live_log_missing = []
            st.session_state.stop_sync_event = threading.Event()

            thread_kwargs = {
                'store_url': st.session_state.shopify_store, 
                'access_token': st.session_state.shopify_token,
                'sentos_api_url': st.session_state.sentos_api_url, 
                'sentos_api_key': st.session_state.sentos_api_key,
                'sentos_api_secret': st.session_state.sentos_api_secret, 
                'sentos_cookie': st.session_state.sentos_cookie,
                'test_mode': missing_test_mode, 
                'max_workers': max_workers,
                'progress_callback': st.session_state.progress_queue.put,
                'stop_event': st.session_state.stop_sync_event
            }
            
            thread = threading.Thread(
                target=sync_missing_products_only, 
                kwargs=thread_kwargs, 
                daemon=True
            )
            st.session_state.missing_sync_thread = thread
            thread.start()
            st.rerun()

    st.markdown("---")
    with st.expander("✨ Özellik: SKU ile Tekil Ürün Güncelle", expanded=True):
        st.info("Sentos'taki bir ürünün model kodunu (SKU) girerek Shopify'daki karşılığını anında ve tam olarak güncelleyebilirsiniz.")
        sku_to_sync = st.text_input("Model Kodu (SKU)", placeholder="Örn: V-123-ABC")
        
        if st.button("🔄 Ürünü Bul ve Senkronize Et", use_container_width=True, disabled=not sync_ready):
            if not sku_to_sync:
                st.warning("Lütfen bir SKU girin.")
            else:
                with st.spinner(f"'{sku_to_sync}' SKU'lu ürün aranıyor ve senkronize ediliyor..."):
                    result = sync_single_product_by_sku(
                        store_url=st.session_state.shopify_store, access_token=st.session_state.shopify_token,
                        sentos_api_url=st.session_state.sentos_api_url, sentos_api_key=st.session_state.sentos_api_key,
                        sentos_api_secret=st.session_state.sentos_api_secret, sentos_cookie=st.session_state.sentos_cookie,
                        sku=sku_to_sync
                    )
                if result.get('success'):
                    product_name = result.get('product_name', sku_to_sync)
                    changes = result.get('changes', [])
                    
                    st.success(f"✅ '{product_name}' ürünü başarıyla güncellendi.")
                    
                    if changes:
                        st.markdown("**Yapılan Kontroller ve İşlemler:**")
                        change_log = ""
                        for change in changes:
                            change_log += f"- {change}\n"
                        st.info(change_log)
                    else:
                        st.info("Sistem herhangi bir işlem raporlamadı.")

                else:
                    st.error(f"❌ Hata: {result.get('message')}")