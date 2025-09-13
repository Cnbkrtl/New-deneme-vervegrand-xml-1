# gsheets_manager.py

import gspread
from gspread_dataframe import set_with_dataframe, get_dataframe
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st
import pandas as pd
import logging
import time

# Loglama konfigürasyonu
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Google Sheets'e bağlan
@st.cache_resource(ttl=3600)
def get_gsheets_client():
    try:
        if "gspread_creds" not in st.session_state:
            creds_json = st.secrets["gcp_service_account"]
            st.session_state.gspread_creds = creds_json

        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.session_state.gspread_creds, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        logging.info("Google Sheets bağlantısı başarılı.")
        return client
    except Exception as e:
        logging.error(f"Google Sheets bağlantı hatası: {e}")
        st.error("Google Sheets'e bağlanılamadı. Lütfen kimlik bilgilerini kontrol edin.")
        return None

def save_pricing_data_to_gsheets(main_df, discount_df, wholesale_df, variants_df):
    """Fiyat verilerini (ana, indirimli, toptan) ve varyant verilerini Google E-Tablolar'a kaydeder."""
    try:
        client = get_gsheets_client()
        if not client:
            return False, None
        
        spreadsheet_name = f"Vervegrand_Fiyatlandirma_{time.strftime('%Y%m%d_%H%M%S')}"
        sh = client.create(spreadsheet_name)
        
        sh.share(st.secrets["gcp_service_account"]["client_email"], perm_type='user', role='writer')
        
        sh.add_worksheet(title="Ana Fiyatlar", rows=main_df.shape[0], cols=main_df.shape[1])
        ws_main = sh.worksheet("Ana Fiyatlar")
        set_with_dataframe(ws_main, main_df)
        
        ws_discount = sh.add_worksheet(title="İndirimli Fiyatlar", rows=discount_df.shape[0], cols=discount_df.shape[1])
        set_with_dataframe(ws_discount, discount_df)
        
        ws_wholesale = sh.add_worksheet(title="Toptan Fiyatlar", rows=wholesale_df.shape[0], cols=wholesale_df.shape[1])
        set_with_dataframe(ws_wholesale, wholesale_df)

        ws_variants = sh.add_worksheet(title="Varyantlar", rows=variants_df.shape[0], cols=variants_df.shape[1])
        set_with_dataframe(ws_variants, variants_df)
        
        logging.info(f"Fiyat verileri Google E-Tablolar'a kaydedildi: {sh.url}")
        return True, sh.url
        
    except Exception as e:
        logging.error(f"Fiyat verileri Google E-Tablolar'a kaydedilemedi: {e}")
        st.error(f"Kaydetme hatası: {e}")
        return False, None

def load_pricing_data_from_gsheets():
    """Son oluşturulan Google E-Tablosunu bulur ve fiyat verilerini yükler."""
    try:
        client = get_gsheets_client()
        if not client:
            return None, None
            
        list_of_spreadsheets = client.openall()
        spreadsheets = [s for s in list_of_spreadsheets if s.title.startswith('Vervegrand_Fiyatlandirma')]
        if not spreadsheets:
            st.warning("Hiç 'Vervegrand_Fiyatlandirma' dosyası bulunamadı.")
            return None, None
            
        latest_spreadsheet = sorted(spreadsheets, key=lambda s: s.updated, reverse=True)[0]
        
        ws_main = latest_spreadsheet.worksheet("Ana Fiyatlar")
        ws_variants = latest_spreadsheet.worksheet("Varyantlar")
        
        main_df = get_dataframe(ws_main)
        variants_df = get_dataframe(ws_variants)

        main_df.dropna(how='all', axis=0, inplace=True)
        main_df.dropna(how='all', axis=1, inplace=True)
        
        variants_df.dropna(how='all', axis=0, inplace=True)
        variants_df.dropna(how='all', axis=1, inplace=True)
        
        logging.info(f"Veriler '{latest_spreadsheet.title}' dosyasından yüklendi.")
        return main_df, variants_df

    except Exception as e:
        logging.error(f"Google E-Tablolar'dan veri yüklenirken hata oluştu: {e}")
        st.error(f"Veri yükleme hatası: {e}")
        return None, None