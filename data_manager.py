# data_manager.py

import os
import json
from cryptography.fernet import Fernet

# config_manager ile aynı anahtarı ve temel dosya adlarını kullanacağız
KEY_FILE = ".secret.key"
DATA_CACHE_DIR = "data_cache" # Veri dosyaları için ayrı bir klasör

def load_key():
    """Şifreleme anahtarını dosyadan yükler veya yoksa yenisini oluşturur."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
        return key

def _get_user_data_file(username):
    """Kullanıcıya özel veri dosyasının yolunu döndürür."""
    if not os.path.exists(DATA_CACHE_DIR):
        os.makedirs(DATA_CACHE_DIR)
    return os.path.join(DATA_CACHE_DIR, f"data_{username}.enc")

def save_user_data(username, **data):
    """Belirtilen kullanıcı için verilen sözlüğü şifreleyerek dosyaya kaydeder."""
    if not username:
        print("Veri kaydetmek için kullanıcı adı gerekli.")
        return False
    
    file_path = _get_user_data_file(username)
    key = load_key()
    fernet = Fernet(key)
    
    try:
        data_to_encrypt = json.dumps(data).encode('utf-8')
        encrypted_data = fernet.encrypt(data_to_encrypt)
        
        with open(file_path, "wb") as file:
            file.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Kullanıcı verisi '{username}' kaydedilirken hata: {e}")
        return False

def load_user_data(username):
    """Belirtilen kullanıcının verilerini dosyadan okur ve şifresini çözer."""
    if not username:
        return {}
        
    file_path = _get_user_data_file(username)
    if not os.path.exists(file_path):
        return {}

    key = load_key()
    fernet = Fernet(key)
    
    try:
        with open(file_path, "rb") as file:
            encrypted_data = file.read()
        
        if not encrypted_data:
            return {}
            
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as e:
        print(f"Kullanıcı verisi '{username}' yüklenirken hata: {e}")
        # Hata durumunda bozuk dosyayı silerek temiz bir başlangıç sağla
        os.remove(file_path)
        return {}

def delete_user_data(username):
    """Belirtilen kullanıcının veri dosyasını siler."""
    if not username:
        return False
    
    file_path = _get_user_data_file(username)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"Kullanıcı veri dosyası '{file_path}' silinirken hata: {e}")
            return False
    return True # Dosya zaten yoksa başarılı say