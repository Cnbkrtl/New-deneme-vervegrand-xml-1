# 🔄 XML to Shopify Sync - Streamlit App

## 📋 Özellikler

Bu Streamlit uygulaması, JavaScript uygulamasındaki **tüm fonksiyonları** aynen Python'a migrate eder:

### ✅ Migrate Edilen Fonksiyonlar:

**JavaScript Settings.jsx → Python Sidebar Settings:**
- `handleShopify()` → `test_shopify_connection()`
- `handleXML()` → `test_xml_connection()`
- Shopify API credentials management
- Connection testing

**JavaScript Dashboard.jsx → Python Main Interface:**
- `startSync()` → Streamlit sync button
- `handleFastMode()` → Fast Mode checkbox
- Progress tracking ve result display
- Error handling ve detailed results

**JavaScript api-chunked.js → Python shopify_sync.py:**
- `handleSyncBatch()` → `sync_products()`
- `getShopifyProducts()` → `ShopifyAPI.get_products_by_sku()`
- `createShopifyProduct()` → `ShopifyAPI.create_product()`
- `updateShopifyProduct()` → `ShopifyAPI.update_product()`
- `parseXMLAdvanced()` → `XMLProcessor.parse_xml_advanced()`
- `parseUrunXMLAdvanced()` → `XMLProcessor.parse_urun_xml_advanced()`
- Rate limiting ve error handling
- Chunked processing mantığı

### 🚀 Avantajlar:
- ❌ **Netlify 26 saniye timeout limit yok**
- ❌ **504 Gateway Timeout hatası yok**
- ✅ **Direkt Shopify API bağlantısı**
- ✅ **Sınırsız processing süresi**
- ✅ **Real-time progress tracking**
- ✅ **Gelişmiş hata yönetimi**

## 🛠️ Kurulum

### 1. Python'u İndir ve Yükle
- [Python 3.9+ indirin](https://www.python.org/downloads/)
- Kurulum sırasında "Add Python to PATH" seçeneğini işaretleyin

### 2. Gerekli Paketleri Yükle
```bash
pip install -r requirements.txt
```

Alternatif olarak manuel kurulum:
```bash
pip install streamlit==1.28.1 requests==2.31.0 pandas==2.1.1 lxml==4.9.3
```

### 3. Uygulamayı Çalıştır
```bash
streamlit run streamlit_app.py
```

## 📚 Kullanım

1. **⚙️ Settings (Sidebar):**
   - Shopify Store URL'inizi girin
   - Shopify Access Token'ınızı girin
   - XML URL'inizi girin
   - Connection test'leri yapın

2. **🧪 Connection Tests:**
   - "🏪 Test Shopify" ile Shopify bağlantısını test edin
   - "📄 Test XML" ile XML dosyasını test edin
   - ⚡ Fast Mode: İlk 100KB XML analizi

3. **🚀 Synchronization:**
   - ⚡ Hızlı Mod: Tüm ürünleri işler (JavaScript Fast Mode)
   - 🧪 Test Mode: Sadece ilk 5 ürünü işler
   - Real-time progress tracking
   - Detaylı sonuçlar ve CSV export

## 🔧 Teknik Detaylar

### API Rate Limiting
- Shopify API rate limit'leri otomatik kontrol edilir
- 500ms minimum request interval
- `X-Shopify-Shop-Api-Call-Limit` header tracking

### XML Processing
- CDATA section parsing
- Advanced product data extraction
- Error handling ve validation
- Fast mode ile partial content fetch

### Shopify Product Management
- SKU-based product matching
- Handle generation ve normalization
- Variant güncelleme
- Tag generation (kategori, stok durumu, fiyat aralığı)

## 🆚 JavaScript vs Python Karşılaştırma

| Fonksiyon | JavaScript | Python | Status |
|-----------|------------|--------|--------|
| Shopify Test | `handleShopify()` | `test_shopify_connection()` | ✅ |
| XML Test | `handleXML()` | `test_xml_connection()` | ✅ |
| Sync Process | `handleSyncBatch()` | `sync_products()` | ✅ |
| Product Search | `getShopifyProducts()` | `get_products_by_sku()` | ✅ |
| Product Create | `createShopifyProduct()` | `create_product()` | ✅ |
| Product Update | `updateShopifyProduct()` | `update_product()` | ✅ |
| XML Parse | `parseXMLAdvanced()` | `parse_xml_advanced()` | ✅ |
| Rate Limiting | Custom logic | `wait_for_rate_limit()` | ✅ |
| Error Handling | Try-catch | Exception handling | ✅ |

## 🚨 Netlify Limitasyonları Çözüldü

### Önceki Problemler:
- ❌ 26 saniye function timeout
- ❌ 504 Gateway Timeout errors
- ❌ Memory limitations
- ❌ Serverless function constraints

### Streamlit Çözümü:
- ✅ Sınırsız processing süresi
- ✅ Direct API connections
- ✅ Local resource kullanımı
- ✅ Real-time monitoring

## 📝 Notlar

- Tüm JavaScript fonksiyonları mantık olarak aynen korunmuştur
- Python'a özgü optimizasyonlar eklenmiştir
- Error handling geliştirilmiştir
- Progress tracking daha detaylıdır
- CSV export özelliği eklenmiştir

## 🆘 Sorun Giderme

### Python Bulunamadı Hatası:
```bash
# Python'un yüklü olduğunu kontrol edin
python --version

# Alternatif komutlar deneyin
python3 --version
py --version
```

### Paket Kurulum Hataları:
```bash
# pip'i güncelle
python -m pip install --upgrade pip

# Gerekli paketleri tek tek yükle
python -m pip install streamlit
python -m pip install requests
python -m pip install pandas
python -m pip install lxml
```

### Port Hatası:
```bash
# Farklı port kullan
streamlit run streamlit_app.py --server.port 8502
```
