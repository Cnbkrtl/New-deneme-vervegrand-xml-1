# data_manager.py

import streamlit as st
import os
import json
from cryptography.fernet import Fernet

DATA_CACHE_DIR = "data_cache" # Veri dosyaları için ayrı bir klasör

def get_fernet():
    """Streamlit secrets'tan Fernet anahtarını yükler ve bir Fernet nesnesi döndürür."""
    fernet_key = st.secrets.get("FERNET_KEY")
    if not fernet_key:
        raise ValueError("Streamlit secrets'ta 'FERNET_KEY' tanımlanmamış. Lütfen secrets.toml dosyanızı kontrol edin.")
    return Fernet(fernet_key.encode('utf-8'))

def _get_user_data_file(username):
    """Kullanıcıya özel veri dosyasının yolunu döndürür."""
    if not os.path.exists(DATA_CACHE_DIR):
        os.makedirs(DATA_CACHE_DIR)
    return os.path.join(DATA_CACHE_DIR, f"data_{username}.enc")

def save_user_data(username, **data):
    """Belirtilen kullanıcı için verilen sözlüğü şifreleyerek dosyaya kaydeder."""
    if not username:
        return False
    
    file_path = _get_user_data_file(username)
    fernet = get_fernet()
    
    try:
        data_to_encrypt = json.dumps(data).encode('utf-8')
        encrypted_data = fernet.encrypt(data_to_encrypt)
        with open(file_path, "wb") as file:
            file.write(encrypted_data)
        return True
    except Exception as e:
        st.error(f"Kullanıcı verisi '{username}' kaydedilirken hata: {e}")
        return False

def load_user_data(username):
    """Belirtilen kullanıcının verilerini dosyadan okur ve şifresini çözer."""
    if not username:
        return {}
        
    file_path = _get_user_data_file(username)
    if not os.path.exists(file_path):
        return {}

    fernet = get_fernet()
    
    try:
        with open(file_path, "rb") as file:
            encrypted_data = file.read()
        if not encrypted_data: return {}
            
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as e:
        st.warning(f"Kullanıcı verisi '{username}' yüklenirken bir sorun oluştu, veri sıfırlanıyor. Hata: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return {}