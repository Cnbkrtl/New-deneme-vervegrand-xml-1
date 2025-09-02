# Comprehensive Shopify-Sentos Sync System

## 🎯 Overview
This is a comprehensive synchronization system that enables bidirectional data exchange between Shopify and Sentos platforms:

- **Products Sync**: Sentos → Shopify (Product information, inventory, prices, variants)
- **Orders Sync**: Shopify → Sentos (Order processing, customer data, fulfillment)

## 🚀 Features

### Product Synchronization (Sentos → Shopify)
- ✅ Fetch products from Sentos API with multiple authentication methods
- ✅ Search existing products in Shopify by name and SKU
- ✅ Create new products with complete variant information
- ✅ Update existing products (title, description, prices, inventory, tags)
- ✅ Handle multiple product variants with colors, models, and sizes
- ✅ Sync stock levels from multiple warehouses
- ✅ Progress tracking and detailed results reporting

### Order Synchronization (Shopify → Sentos)
- ✅ Fetch orders from Shopify with configurable filters
- ✅ Transform Shopify order format to Sentos API format
- ✅ Handle customer information and billing/shipping addresses
- ✅ Map order items with quantities, prices, and SKUs
- ✅ Check for existing orders to prevent duplicates
- ✅ Create or update orders in Sentos system
- ✅ Status mapping between platforms

### Application Interface
- ✅ Modern Streamlit web interface
- ✅ Dashboard with connection status overview
- ✅ Settings page with encrypted credential storage
- ✅ Automatic API connection testing
- ✅ Sync page with test/full mode options
- ✅ Activity logs with filtering capabilities
- ✅ Progress tracking during sync operations

## 📋 Technical Architecture

### Core Components

1. **SentosAPI Class**
   - Multi-authentication method support (Custom Headers, Bearer Token, Basic Auth, Token Auth)
   - Automatic authentication method detection
   - Product fetching from `/products` endpoint
   - Individual product retrieval by ID

2. **ProductSyncManager Class**
   - Intelligent product matching by name and SKU
   - Shopify product cache for improved performance
   - Variant synchronization with color/model mapping
   - Comprehensive update logic for all product fields

3. **OrderSyncManager Class**
   - Order transformation between platform formats
   - Customer and address data mapping
   - Duplicate order detection and handling
   - Status mapping between Shopify and Sentos

4. **ShopifyAPI Class** (Enhanced)
   - Rate limiting compliance
   - Product cache management
   - Comprehensive error handling
   - RESTful API integration

### Security Features
- ✅ Fernet encryption for API credentials
- ✅ Secure session state management
- ✅ Encrypted credential storage
- ✅ No plain text credential exposure

### Sync Options
- **Test Mode**: Process limited items (5 products/orders) for testing
- **Full Mode**: Process all available data
- **Configurable Filters**: Select specific sync operations
- **Progress Tracking**: Real-time sync progress with detailed messages

## 🔧 Configuration

### Required Credentials
1. **Shopify Settings**
   - Store URL (mystore.myshopify.com)
   - Admin API Access Token
   
2. **Sentos Settings**
   - API Base URL
   - API Key (Anahtar)
   - API Secret (Şifre)

### Supported Authentication Methods (Auto-detected)
- Custom Headers (`X-API-Key`, `X-API-Secret`)
- Bearer Token (`Authorization: Bearer`)
- Basic Authentication
- Token Authentication (`Authorization: Token`)

## 📊 Sync Results

### Product Sync Results
- **Created**: New products added to Shopify
- **Updated**: Existing products modified in Shopify
- **Failed**: Products that couldn't be processed
- **Skipped**: Products that needed no changes
- **Total**: All products processed

### Order Sync Results
- **Created**: New orders added to Sentos
- **Updated**: Existing orders modified in Sentos
- **Failed**: Orders that couldn't be processed
- **Total**: All orders processed

## 🔄 Workflow Examples

### Product Sync Workflow
1. Load Shopify products into cache
2. Fetch products from Sentos API
3. For each Sentos product:
   - Search in Shopify by name/SKU
   - If found: Update product fields and variants
   - If not found: Create new product with variants
   - Update inventory from Sentos stock data
4. Report sync statistics and details

### Order Sync Workflow
1. Fetch recent orders from Shopify
2. For each order:
   - Transform to Sentos format
   - Extract customer and address information
   - Map order items and quantities
   - Check if order exists in Sentos
   - Create or update order in Sentos
3. Report sync statistics and details

## 🛡️ Error Handling
- Comprehensive exception handling at all levels
- Detailed error messages with context
- Rate limiting compliance to prevent API blocks
- Automatic retry mechanisms for transient failures
- Progress preservation during interruptions

## 📈 Performance Features
- Product cache to minimize API calls
- Batch processing with configurable limits
- Rate limiting to respect API quotas
- Efficient data transformation algorithms
- Memory-optimized data structures

## 🚦 Status Indicators
- **Connected** ✅: API working properly
- **Failed** ❌: Connection issues detected
- **Pending** ⏳: Testing in progress

## 📝 Logging System
- Real-time activity logging
- Filterable log types (Success, Error, Info)
- Automatic log rotation (100 entries max)
- Timestamp tracking for all operations

## 🔧 Future Enhancements
- [ ] Webhook integration for real-time sync
- [ ] Advanced filtering options
- [ ] Bulk operations optimization
- [ ] Custom field mapping
- [ ] Automated scheduling
- [ ] Performance analytics dashboard

## 🔗 API Endpoints Used

### Shopify Admin API
- `GET /admin/api/2023-10/shop.json` - Store information
- `GET /admin/api/2023-10/products.json` - Product listing
- `POST /admin/api/2023-10/products.json` - Create products
- `PUT /admin/api/2023-10/products/{id}.json` - Update products
- `GET /admin/api/2023-10/orders.json` - Order listing

### Sentos API
- `GET /products` - Product listing
- `GET /products/{id}` - Individual product
- `GET /orders` - Order listing (search)
- `POST /orders` - Create orders
- `PUT /orders/{id}` - Update orders

## 📞 Support
For any issues or questions regarding the sync system, check the activity logs for detailed error messages and ensure all API credentials are properly configured.
