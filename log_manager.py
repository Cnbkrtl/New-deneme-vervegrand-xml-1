import json
import os
from datetime import datetime

LOG_FILE = "sync_history.json"

def load_logs():
    """
    Senkronizasyon geçmişini log dosyasından yükler.
    """
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Dosya bozuksa veya okunamıyorsa boş liste döndür
        return []

def save_log(sync_results):
    """
    Yeni bir senkronizasyon sonucunu log dosyasına kaydeder.
    """
    logs = load_logs()
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "stats": sync_results.get('stats', {}),
        "details": sync_results.get('details', [])
    }
    
    # Yeni kaydı listenin başına ekle
    logs.insert(0, log_entry)
    
    # Dosyanın çok büyümemesi için sadece son 50 kaydı tut
    if len(logs) > 50:
        logs = logs[:50]
        
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Log dosyası kaydedilirken hata oluştu: {e}")
