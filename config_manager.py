import streamlit as st
from cryptography.fernet import Fernet
import json
import os

# Anahtar dosyasının adı
KEY_FILE = ".secret.key"
# Şifrelenmiş kimlik bilgileri dosyasının adı
CREDS_FILE = "credentials.enc"

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

def load_all_keys():
    """
    Tüm kullanıcıların şifrelenmiş ayarlarını dosyadan yükler ve çözer.
    Dosya yapısı: { "kullanici1": {"ayar1": "deger1"}, "kullanici2": {"ayar2": "deger2"} }
    """
    if not os.path.exists(CREDS_FILE):
        return {}
    
    try:
        key = load_key()
        fernet = Fernet(key)

        with open(CREDS_FILE, "rb") as file:
            encrypted_data = file.read()
        
        if not encrypted_data:
            return {}
            
        decrypted_data = fernet.decrypt(encrypted_data)
        credentials = json.loads(decrypted_data.decode('utf-8'))
        return credentials
    except Exception as e:
        print(f"Ayarları yüklerken hata oluştu: {e}")
        if os.path.exists(CREDS_FILE):
            os.remove(CREDS_FILE)
        return {}

def _save_all_creds(credentials_dict):
    """
    Verilen TÜM sözlüğü (tüm kullanıcıların verilerini) şifreleyerek dosyaya kaydeder.
    Bu fonksiyon dahili kullanım içindir.
    """
    try:
        key = load_key()
        fernet = Fernet(key)
        
        data_to_encrypt = json.dumps(credentials_dict).encode('utf-8')
        encrypted_data = fernet.encrypt(data_to_encrypt)

        with open(CREDS_FILE, "wb") as file:
            file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Ayarları kaydederken hata oluştu: {e}")
        return False

def save_user_keys(username, **kwargs):
    """
    Belirtilen kullanıcı için verilen anahtar-değer çiftlerini günceller.
    Değer boş ise mevcut anahtarı siler.
    """
    if not username:
        print("Ayarları kaydetmek için kullanıcı adı gerekli.")
        return False
    
    all_credentials = load_all_keys()
    user_credentials = all_credentials.get(username, {})
    
    # Sadece kwargs içinde gelen değerleri güncelle
    for key, value in kwargs.items():
        # Değer doluysa kaydet/güncelle (JSON için strip() kullanmıyoruz)
        if value:
            user_credentials[key] = value
        # Değer boş olarak geldiyse ve daha önce kayıtlıysa, bu anahtarı sil
        elif key in user_credentials:
            del user_credentials[key]

    all_credentials[username] = user_credentials
    return _save_all_creds(all_credentials)