import streamlit as st
from cryptography.fernet import Fernet
import json
import os

# Anahtar dosyasının adı
KEY_FILE = ".secret.key"
# Şifrelenmiş kimlik bilgileri dosyasının adı
CREDS_FILE = "credentials.enc"
# Şifrelenecek anahtarların listesi
KEYS_TO_ENCRYPT = [
    'shopify_token', 
    'sentos_api_key', 
    'sentos_api_secret', 
    'sentos_cookie'  # YENİ: Cookie de şifrelenecek
]

def generate_and_save_key():
    """Yeni bir şifreleme anahtarı oluşturur ve dosyaya kaydeder."""
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    """Şifreleme anahtarını dosyadan yükler veya yoksa yenisini oluşturur."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        return generate_and_save_key()

def save_all_keys(**kwargs):
    """
    Verilen tüm anahtar-değer çiftlerini şifreleyerek dosyaya kaydeder.
    """
    try:
        key = load_key()
        fernet = Fernet(key)
        
        credentials_to_save = {}
        for k, v in kwargs.items():
            if v:  # Sadece dolu olan alanları kaydet
                credentials_to_save[k] = v.strip()

        data_to_encrypt = json.dumps(credentials_to_save).encode('utf-8')
        encrypted_data = fernet.encrypt(data_to_encrypt)

        with open(CREDS_FILE, "wb") as file:
            file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Ayarları kaydederken hata oluştu: {e}")
        return False

def load_all_keys():
    """
    Şifrelenmiş ayarları dosyadan yükler ve çözer.
    """
    if not os.path.exists(CREDS_FILE):
        return {}
    
    try:
        key = load_key()
        fernet = Fernet(key)

        with open(CREDS_FILE, "rb") as file:
            encrypted_data = file.read()
        
        decrypted_data = fernet.decrypt(encrypted_data)
        credentials = json.loads(decrypted_data.decode('utf-8'))
        return credentials
    except Exception as e:
        print(f"Ayarları yüklerken hata oluştu: {e}")
        # Hata durumunda eski dosyayı silerek sıfırlamayı kolaylaştır
        if os.path.exists(CREDS_FILE):
            os.remove(CREDS_FILE)
        return {}