import requests
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ping_services():
    """Servisleri uyanık tutmak için ping gönder"""
    services = [
        "https://app-and-worker.onrender.com/_stcore/health",
        "https://streamlit-app.onrender.com/_stcore/health",
        "https://app-and-worker.onrender.com",
    ]
    
    for service_url in services:
        try:
            response = requests.get(service_url, timeout=30)
            logger.info(f"✅ Ping successful: {service_url} - Status: {response.status_code}")
            time.sleep(1)  # Servisler arası kısa bekleme
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Ping failed: {service_url} - Error: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {service_url} - Error: {str(e)}")

if __name__ == "__main__":
    logger.info(f"🔄 Starting keep-alive ping at {datetime.now()}")
    ping_services()
    logger.info("✨ Keep-alive ping completed")
