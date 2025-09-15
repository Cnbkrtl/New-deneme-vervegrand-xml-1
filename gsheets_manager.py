# gsheets_manager.py

import streamlit as st
import pandas as pd
import json

# Try-except bloğu ile gerekli tüm bağımlılıkları kontrol et
try:
    import gspread
    from gspread_dataframe import set_with_dataframe
    from google.oauth2.service_account import Credentials
    import gspread.exceptions
except ImportError as e:
    st.error(f"Gerekli Google Sheets bağımlılıkları yüklenemedi. Lütfen 'requirements.txt' dosyanızı kontrol edin ve `pip install -r requirements.txt` komutunu çalıştırın. Hata: {e}")
    st.stop()
    
# --- Sabitler ---
SPREADSHEET_NAME = "Vervegrand Fiyat Yönetim"
SHEET_NAMES = {
    "main": "Ana Fiyat",
    "discount": "İndirimli Fiyat",
    "wholesale": "Toptan Fiyat",
    "variants": "Varyantlar"
}

# --- Bağlantı Fonksiyonu ---
@st.cache_resource(ttl=3600)
def get_gsheet_client():
    """Google Service Account kullanarak gspread istemcisini başlatır ve önbelleğe alır."""
    try:
        creds_json_str = st.secrets.get("GCP_SERVICE_ACCOUNT_JSON")
        if not creds_json_str:
            raise ValueError("Google Service Account anahtarı Streamlit Secrets'ta bulunamadı.")
        
        creds_dict = json.loads(creds_json_str)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Google Sheets'e bağlanırken bir hata oluştu: {e}. Lütfen secrets dosyanızı kontrol edin.")
        st.stop()


# --- Veri Kaydetme Fonksiyonu ---
def save_pricing_data_to_gsheets(main_df, discount_df, wholesale_df, variants_df):
    """Fiyat verilerini (ana, indirimli, toptan) ve varyant verilerini Google E-Tablolar'a kaydeder."""
    try:
        client = get_gsheet_client()
        
        # E-Tabloyu aç veya oluştur
        try:
            spreadsheet = client.open(SPREADSHEET_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            st.info(f"'{SPREADSHEET_NAME}' bulunamadı, yeni bir e-tablo oluşturuluyor...")
            spreadsheet = client.create(SPREADSHEET_NAME)
            # Servis hesabını yetkilendir
            creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
            spreadsheet.share(creds_dict['client_email'], perm_type='user', role='writer')

        data_map = {
            SHEET_NAMES["main"]: main_df,
            SHEET_NAMES["discount"]: discount_df,
            SHEET_NAMES["wholesale"]: wholesale_df,
            SHEET_NAMES["variants"]: variants_df
        }

        for sheet_name, df in data_map.items():
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                st.info(f"'{sheet_name}' sayfası güncelleniyor...")
            except gspread.exceptions.WorksheetNotFound:
                st.info(f"'{sheet_name}' sayfası bulunamadı, yeni sayfa oluşturuluyor...")
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="50")
            
            worksheet.clear()
            # DataFrame'i yazarken NaN değerlerini boş string ile değiştir
            set_with_dataframe(worksheet, df.fillna(""), allow_formulas=False, resize=True)
            
        return True, spreadsheet.url
    except Exception as e:
        st.error(f"Google E-Tablolar'a veri kaydedilirken hata oluştu: {e}")
        return False, None

# --- Veri Yükleme Fonksiyonu ---
def load_pricing_data_from_gsheets():
    """Google E-Tablosundan 'Ana Fiyat' ve 'Varyantlar' sayfalarını okur ve DataFrame olarak döndürür."""
    try:
        client = get_gsheet_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        ws_main = spreadsheet.worksheet(SHEET_NAMES["main"])
        ws_variants = spreadsheet.worksheet(SHEET_NAMES["variants"])
        
        st.info(f"'{SPREADSHEET_NAME}' e-tablosundan veriler okunuyor...")
        
        data_main = ws_main.get_all_records()
        df_main = pd.DataFrame(data_main) if data_main else pd.DataFrame()
        
        data_variants = ws_variants.get_all_records()
        df_variants = pd.DataFrame(data_variants) if data_variants else pd.DataFrame()

        # --- YENİ EKLENEN KISIM BURASI ---
        # Veri tipi tutarsızlığını ve Arrow hatasını kalıcı olarak çözmek için
        # MODEL KODU ve base_sku sütunlarının veri tipini metin (string) olarak zorunlu kılıyoruz.
        if not df_main.empty and 'MODEL KODU' in df_main.columns:
            df_main['MODEL KODU'] = df_main['MODEL KODU'].astype(str)
        
        if not df_variants.empty and 'MODEL KODU' in df_variants.columns:
            df_variants['MODEL KODU'] = df_variants['MODEL KODU'].astype(str)
            if 'base_sku' in df_variants.columns:
                df_variants['base_sku'] = df_variants['base_sku'].astype(str)
        # --- YENİ KISIM BİTİŞ ---

        # Sayısal olması gereken sütunları sayısal yap
        numeric_cols = ['ALIŞ FİYATI', 'SATIS_FIYATI_KDVSIZ', 'NIHAI_SATIS_FIYATI', 'KÂR', 'KÂR ORANI (%)']
        for col in numeric_cols:
            if col in df_main.columns:
                df_main[col] = pd.to_numeric(df_main[col], errors='coerce')
        
        return df_main, df_variants
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.warning(f"'{SPREADSHEET_NAME}' adında bir Google E-Tablosu bulunamadı.")
        return None, None
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"E-tabloda gerekli sayfalar bulunamadı.")
        return None, None
    except Exception as e:
        st.error(f"Google E-Tablolardan veri okunurken bir hata oluştu: {e}")
        return None, None