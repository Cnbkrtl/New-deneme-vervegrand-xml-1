# 🔄 XML to Shopify Sync - Streamlit Edition

**Professional XML to Shopify synchronization tool built with Python & Streamlit**

> ⚠️ **Migration Complete**: This project has been fully migrated from React/Netlify to Python/Streamlit to eliminate timeout limitations and provide direct API access.

## 🚀 Features

- **✅ Direct Shopify API Integration** - No proxy limitations
- **✅ Unlimited Processing Time** - No 26-second timeout restrictions  
- **✅ Real-time Progress Tracking** - Live sync monitoring
- **✅ Advanced XML Parsing** - CDATA support, error handling
- **✅ Smart Product Matching** - SKU-based matching with similarity algorithms
- **✅ Bulk Operations** - Create/update products with variants
- **✅ Test Mode** - Process first 5 products for testing
- **✅ Fast Mode** - Optimized for large XML files
- **✅ CSV Export** - Download detailed sync results

## 📋 Migration Summary

| Component | Before (JavaScript) | After (Python) | Status |
|-----------|-------------------|----------------|--------|
| Frontend | React + Vite | Streamlit | ✅ Complete |
| Backend | Netlify Functions | Direct Python | ✅ Complete |
| Timeout | 26 seconds | Unlimited | ✅ Solved |
| API Access | Proxied | Direct | ✅ Improved |
| Progress | Basic | Real-time | ✅ Enhanced |

## 🛠️ Quick Start

### 1. Install Python
Download Python 3.9+ from [python.org](https://www.python.org/downloads/)
- ⚠️ **Important**: Check "Add Python to PATH" during installation

### 2. Run the App
**Windows (Easy Way):**
```bash
# Just double-click this file:
start_app.bat
```

**Manual Way:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

### 3. Configure & Sync
1. Open `http://localhost:8501` in your browser
2. Enter your Shopify credentials in the sidebar
3. Add your XML URL
4. Test connections
5. Start synchronization!

## 📁 Project Structure

```
📦 streamlit-shopify-sync/
├── 🐍 streamlit_app.py      # Main Streamlit application
├── 🔧 shopify_sync.py       # Core sync logic & API functions
├── 📋 requirements.txt      # Python dependencies
├── 🚀 start_app.bat         # Easy Windows launcher
├── 📖 README.md             # This file
└── 📚 README_STREAMLIT.md   # Detailed technical docs
```

## 🔧 Configuration

### Shopify Settings
- **Store URL**: `your-store.myshopify.com`
- **Access Token**: Admin API access token
- **Required Permissions**: `read_products`, `write_products`, `write_inventory`

### XML Format
Supports Sentos XML format with CDATA sections:
```xml
<Urun>
    <StokKodu><![CDATA[PRODUCT-001]]></StokKodu>
    <UrunAdi><![CDATA[Product Name]]></UrunAdi>
    <Aciklama><![CDATA[Product Description]]></Aciklama>
    <SatisFiyati1>99.99</SatisFiyati1>
    <StokMiktari>10</StokMiktari>
    <!-- ... more fields ... -->
</Urun>
```

## 🎯 Sync Process

1. **📄 XML Analysis** - Parse products from XML
2. **🔍 Product Matching** - Find existing products by SKU
3. **🆕 Create New** - Add products that don't exist
4. **🔄 Update Existing** - Sync prices, stock, descriptions
5. **📊 Generate Report** - Detailed results with export

## 🆚 Why Migrate from React/Netlify?

### ❌ Previous Limitations:
- 26-second function timeout causing 504 errors
- Serverless memory constraints  
- Proxy/CORS complications
- Limited debugging capabilities

### ✅ Streamlit Advantages:
- Unlimited processing time
- Direct API connections
- Better error handling
- Real-time progress tracking
- Local resource utilization
- Enhanced debugging

## 📊 Performance

- **Large XML Files**: ✅ No timeout restrictions
- **Bulk Operations**: ✅ Processes thousands of products
- **Memory Usage**: ✅ Efficient streaming
- **API Rate Limits**: ✅ Automatic throttling

## 🚨 Troubleshooting

### Python Not Found
```bash
# Download Python from python.org
# Make sure "Add to PATH" is checked during installation
```

### Port Already in Use
```bash
streamlit run streamlit_app.py --server.port 8502
```

### Dependencies Error
```bash
python -m pip install --upgrade pip
python -m pip install streamlit requests pandas lxml
```

## 🤝 Support

For issues or questions:
1. Check `README_STREAMLIT.md` for detailed docs
2. Review error messages in the Streamlit interface
3. Test connections before running full sync

## 📈 Version History

- **v2.0** - Python/Streamlit migration (Current)
- **v1.x** - React/Netlify version (Deprecated)

---

**Built with ❤️ using Python & Streamlit** | No more timeouts! 🎉
