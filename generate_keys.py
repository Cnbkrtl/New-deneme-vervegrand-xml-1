# generate_keys.py
import bcrypt

# Buraya istediğiniz kadar şifre ekleyip hash'leyebilirsiniz.
passwords_to_hash = ["19519", "Cn1Bkrtl"] 
hashed_passwords = []

for password in passwords_to_hash:
    # Şifreyi byte'a çevir
    password_bytes = password.encode('utf-8')
    # Hash'i oluştur
    salt = bcrypt.gensalt()
    hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)
    # Tekrar string'e çevirip listeye ekle
    hashed_passwords.append(hashed_password_bytes.decode('utf-8'))

print("Hash'lenmiş şifreleriniz aşağıdadır. Bunları kopyalayıp config.yaml dosyasına yapıştırın:")
print(hashed_passwords)