# config_manager.py
import streamlit as st
from cryptography.fernet import Fernet
import json
import os

KEY_FILE = ".secret.key"
CREDS_FILE = "credentials.enc"

def generate_and_save_key():
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        return generate_and_save_key()

def save_user_keys(username, **kwargs):
    """
    Belirtilen kullanıcıya ait anahtar-değer çiftlerini şifreleyerek kaydeder.
    """
    try:
        all_credentials = load_all_keys()  # Mevcut tüm veriyi yükle
        
        user_credentials = all_credentials.get(username, {})
        for k, v in kwargs.items():
            if v:
                user_credentials[k] = v.strip()
            elif k in user_credentials: # Eğer alan boşaltıldıysa sil
                del user_credentials[k]

        all_credentials[username] = user_credentials # O kullanıcıya ait veriyi güncelle

        key = load_key()
        fernet = Fernet(key)
        
        data_to_encrypt = json.dumps(all_credentials).encode('utf-8')
        encrypted_data = fernet.encrypt(data_to_encrypt)

        with open(CREDS_FILE, "wb") as file:
            file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Kullanıcı ayarları kaydedilirken hata: {e}")
        return False

def load_all_keys():
    """
    Tüm kullanıcıların şifrelenmiş ayarlarını dosyadan yükler ve çözer.
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