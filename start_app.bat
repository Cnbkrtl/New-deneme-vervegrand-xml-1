@echo off
echo.
echo ======================================
echo  Shopify-Sentos Sync System
echo ======================================
echo.
echo Starting comprehensive sync system...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)
    echo Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin
    pause
    exit /b 1
)

echo ✅ Python bulundu!

REM Gerekli paketleri yükle
echo 📦 Gerekli paketler yuklenyor...
python -m pip install streamlit requests pandas lxml

if %errorlevel% neq 0 (
    echo ❌ Paket kurulumu basarisiz!
    pause
    exit /b 1
)

echo ✅ Paketler basariyla yuklendi!
echo.

REM Streamlit uygulamasını başlat
echo 🚀 Streamlit uygulamasi baslatiliyor...
echo 🌐 Tarayicinizda http://localhost:8501 acilacak
echo.
echo Uygulamayi kapatmak icin Ctrl+C basin
echo.

REM Email prompt'unu atla
echo. | py -c "import streamlit.cli; streamlit.cli.main(['run', 'streamlit_app.py', '--server.headless=true'])" 2>nul || py -m streamlit run streamlit_app.py

pause
