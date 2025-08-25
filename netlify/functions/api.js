exports.handler = async (event, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  const path = event.path || event.rawUrl || '';
  
  if (path.endsWith('/shopify')) {
    return handleShopify(event, headers);
  }
  if (path.endsWith('/xml')) {
    return handleXML(event, headers);
  }
  if (path.endsWith('/xml-debug')) {
    return handleXMLDebug(event, headers);
  }
  if (path.endsWith('/google')) {
    return handleGoogle(event, headers);
  }
  if (path.endsWith('/sync')) {
    return handleSync(event, headers);
  }

  return {
    statusCode: 404,
    headers,
    body: JSON.stringify({ error: 'Not found' }),
  };
};

async function handleShopify(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { apiKey, apiSecret, storeUrl, accessToken } = JSON.parse(event.body);
  
  try {
    const url = `https://${storeUrl}/admin/api/2023-01/shop.json`;
    const response = await fetch(url, {
      headers: { 'X-Shopify-Access-Token': accessToken }
    });
    
    if (!response.ok) throw new Error(`Shopify API error: ${response.status}`);
    const data = await response.json();
    
    const productsResponse = await fetch(`https://${storeUrl}/admin/api/2023-01/products/count.json`, {
      headers: { 'X-Shopify-Access-Token': accessToken }
    });
    const productsData = await productsResponse.json();
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        status: 'success', 
        data: {
          storeName: data.shop.name,
          productCount: productsData.count || 0,
          lastUpdated: new Date().toISOString(),
          connected: true
        }
      })
    };
  } catch (error) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

async function handleXMLDebug(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { xmlUrl } = JSON.parse(event.body);
  
  try {
    const response = await fetch(xmlUrl);
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlText = await response.text();
    
    // XML'in ilk 2000 karakterini döndür
    const preview = xmlText.substring(0, 2000);
    
    // Temel tag analizi
    const analysis = {
      totalLength: xmlText.length,
      preview: preview,
      tagCounts: {
        urun: (xmlText.match(/<urun[^>]*>/gi) || []).length,
        product: (xmlText.match(/<product[^>]*>/gi) || []).length,
        item: (xmlText.match(/<item[^>]*>/gi) || []).length,
        goods: (xmlText.match(/<goods[^>]*>/gi) || []).length
      },
      sampleStructure: extractSampleProduct(xmlText)
    };
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        status: 'success', 
        data: analysis
      })
    };
  } catch (error) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

// İlk ürünün yapısını çıkar
function extractSampleProduct(xmlText) {
  // İlk ürün tagını bul
  const urunMatch = xmlText.match(/<urun[^>]*>[\s\S]*?<\/urun>/i);
  if (urunMatch) {
    return urunMatch[0].substring(0, 500) + '...';
  }
  
  const productMatch = xmlText.match(/<product[^>]*>[\s\S]*?<\/product>/i);
  if (productMatch) {
    return productMatch[0].substring(0, 500) + '...';
  }
  
  return 'Ürün yapısı bulunamadı';
}

async function handleXML(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { xmlUrl } = JSON.parse(event.body);
  
  try {
    console.log('📄 XML çekiliyor:', xmlUrl);
    
    // Önce HEAD request ile boyutu kontrol et
    try {
      const headResponse = await fetch(xmlUrl, { method: 'HEAD' });
      const contentLength = headResponse.headers.get('content-length');
      if (contentLength) {
        const sizeInMB = parseInt(contentLength) / 1024 / 1024;
        console.log(`📏 XML boyutu: ${sizeInMB.toFixed(2)} MB`);
        
        if (sizeInMB > 20) {
          console.log('⚠️ XML dosyası çok büyük, hafif analiz yapılacak');
        }
      }
    } catch (headError) {
      console.log('ℹ️ HEAD request başarısız, doğrudan XML çekilecek');
    }
    
    // XML fetch için uzun timeout (60 saniye)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 saniye timeout
    
    const response = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Shopify-XML-Sync/1.0',
        'Accept-Encoding': 'gzip, deflate'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    console.log('📄 XML response alındı, text okuma başlıyor...');
    const xmlText = await response.text();
    const xmlSizeMB = xmlText.length / 1024 / 1024;
    console.log(`📄 XML boyutu: ${xmlSizeMB.toFixed(2)} MB`);
    
    // Büyük dosyalar için sadece hafif analiz
    let analysis;
    if (xmlSizeMB > 15) {
      console.log('📄 Büyük dosya - sadece hafif analiz yapılıyor...');
      analysis = analyzeXMLLight(xmlText);
    } else {
      console.log('📄 Normal boyut - tam analiz yapılıyor...');
      analysis = analyzeXMLLight(xmlText); // Şimdilik hep hafif analiz
    }
    console.log('📄 XML analizi tamamlandı');
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        status: 'success', 
        data: {
          products: analysis.products,
          uniqueProducts: analysis.uniqueProducts || analysis.products,
          duplicateCount: analysis.duplicateCount || 0,
          structure: analysis.structure,
          sampleProducts: analysis.sampleProducts || [],
          xmlInfo: analysis.xmlInfo,
          lastUpdated: new Date().toISOString(),
          connected: true,
          healthy: analysis.products > 0
        }
      })
    };
  } catch (error) {
    console.error('❌ XML error:', error);
    if (error.name === 'AbortError') {
      return {
        statusCode: 408,
        headers,
        body: JSON.stringify({ 
          status: 'error', 
          error: 'XML fetch timeout (60s) - dosya çok büyük. Lütfen daha küçük XML dosyası kullanın veya tekrar deneyin.' 
        })
      };
    }
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

// Hafif XML analizi - timeout'u önlemek için
function analyzeXMLLight(xmlText) {
  console.log('🔍 Hafif XML analizi başlıyor...');
  
  // Sadece toplam ürün sayısını say, detayına girme
  const urunCount = (xmlText.match(/<Urun[\s>]/gi) || []).length;
  
  // İlk ürünün bilgilerini al (sample için)
  const firstUrunMatch = xmlText.match(/<Urun[\s>][\s\S]*?<\/Urun>/i);
  let sampleProduct = null;
  
  if (firstUrunMatch) {
    const productXml = firstUrunMatch[0];
    sampleProduct = {
      id: extractXMLValue(productXml, 'id'),
      stokKodu: extractCDATAValue(productXml, 'stok_kodu'),
      urunIsmi: extractCDATAValue(productXml, 'urunismi')?.substring(0, 50) + '...',
      kategori: extractCDATAValue(productXml, 'kategori_ismi')?.substring(0, 30) + '...'
    };
  }
  
  return {
    products: urunCount,
    structure: 'Urunler/Urun',
    sampleProducts: sampleProduct ? [sampleProduct] : [],
    xmlInfo: {
      totalSize: xmlText.length,
      hasStockCodes: xmlText.includes('<stok_kodu>'),
      hasCDATA: xmlText.includes('<![CDATA['),
      hasCategories: xmlText.includes('<kategori_ismi>'),
      encoding: xmlText.includes('utf-8') ? 'UTF-8' : 'Unknown'
    },
    debug: {
      totalUrunTags: urunCount,
      xmlPreview: xmlText.substring(0, 500)
    }
  };
}

async function handleGoogle(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { clientId, apiKey, spreadsheetId } = JSON.parse(event.body);
  
  try {
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?key=${apiKey}`;
    const response = await fetch(url);
    
    if (!response.ok) throw new Error(`Google API error: ${response.status}`);
    const data = await response.json();
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        status: 'success', 
        data: {
          sheetName: data.properties.title,
          sheetCount: data.sheets.length,
          lastUpdated: new Date().toISOString(),
          connected: true
        }
      })
    };
  } catch (error) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

async function handleSync(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  try {
    // API bilgilerini request body'den al
    let requestBody;
    try {
      requestBody = JSON.parse(event.body || '{}');
    } catch (parseError) {
      throw new Error('Invalid JSON in request body: ' + parseError.message);
    }
    
    console.log('📥 Sync request body:', requestBody);
    
    // Gerekli parametreleri kontrol et
    if (!requestBody.xmlUrl) {
      throw new Error('XML URL gerekli');
    }
    if (!requestBody.storeUrl || !requestBody.accessToken) {
      throw new Error('Shopify API bilgileri eksik');
    }
    
    const xmlUrl = requestBody.xmlUrl;
    const shopifyConfig = {
      storeUrl: requestBody.storeUrl,
      accessToken: requestBody.accessToken,
      apiKey: requestBody.apiKey
    };
    
    console.log('🚀 Senkronizasyon başladı...');
    console.log(`📄 XML URL: ${xmlUrl}`);
    console.log(`🏪 Store URL: ${shopifyConfig.storeUrl}`);
    const syncStartTime = Date.now();
    
    // 1. XML'i çek ve analiz et
    console.log('📄 XML verisi çekiliyor...', xmlUrl);
    
    // Sync için daha uzun timeout (60 saniye)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);
    
    const xmlResponse = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Shopify-XML-Sync/1.0'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!xmlResponse.ok) throw new Error(`XML fetch error: ${xmlResponse.status}`);
    
    const xmlText = await xmlResponse.text();
    console.log(`✓ XML çekildi (${(xmlText.length / 1024 / 1024).toFixed(2)} MB)`);
    
    // Memory temizliği için intermediate variables
    const xmlSize = xmlText.length;
    
    // 2. XML'den ürün verilerini çıkar (sadece benzersiz olanları)
    console.log('🔍 XML ürünleri parse ediliyor...');
    const xmlProducts = parseXMLProductsAdvanced(xmlText);
    const xmlProductsLength = xmlProducts.length;
    console.log(`✓ ${xmlProductsLength} benzersiz ürün bulundu`);
    
    // 3. Shopify'daki mevcut ürünleri kontrol et
    console.log('🏪 Shopify ürünleri kontrol ediliyor...');
    const shopifyProducts = await getShopifyProductsAdvanced(shopifyConfig);
    const shopifyProductsLength = shopifyProducts.length;
    console.log(`✓ Shopify'da ${shopifyProductsLength} ürün bulundu`);
    
    // 4. Senkronizasyon işlemini yap
    console.log('⚡ Senkronizasyon işlemi başlıyor...');
    const syncResults = await syncProductsAdvanced(xmlProducts, shopifyProducts, shopifyConfig);
    
    const syncEndTime = Date.now();
    const duration = ((syncEndTime - syncStartTime) / 1000).toFixed(2);
    
    console.log(`✅ Senkronizasyon tamamlandı (${duration}s)`);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          xmlProductsFound: xmlProductsLength,
          shopifyProductsExisting: shopifyProductsLength,
          productsUpdated: syncResults.updated,
          productsCreated: syncResults.created,
          productsSkipped: syncResults.skipped,
          errors: syncResults.errors,
          duration: duration + 's',
          timestamp: new Date().toISOString(),
          details: syncResults.details
        }
      })
    };
  } catch (error) {
    console.error('❌ Senkronizasyon hatası:', error);
    
    let statusCode = 500;
    let errorMessage = error.message;
    
    if (error.name === 'AbortError') {
      statusCode = 408;
      errorMessage = 'Senkronizasyon zaman aşımına uğradı (60s) - XML dosyası çok büyük';
    } else if (error.message.includes('fetch')) {
      statusCode = 502;
      errorMessage = 'XML dosyası indirilemedi - bağlantı hatası';
    } else if (error.message.includes('parse')) {
      statusCode = 422;
      errorMessage = 'XML dosyası parse edilemedi - format hatası';
    }
    
    return {
      statusCode,
      headers,
      body: JSON.stringify({ 
        status: 'error', 
        error: errorMessage,
        originalError: error.message,
        timestamp: new Date().toISOString()
      })
    };
  }
}

// Gelişmiş XML ürün parsing - Sentos XML formatına özel
function parseXMLProductsAdvanced(xmlText) {
  const products = [];
  const processedIds = new Set();
  
  // Sentos XML yapısına göre <Urun> etiketlerini bul
  const urunRegex = /<Urun[\s>][\s\S]*?<\/Urun>/gi;
  let match;
  
  console.log('🔍 XML ürünleri işleniyor...');
  
  while ((match = urunRegex.exec(xmlText))) {
    const productXml = match[0];
    
    try {
      // Ürün bilgilerini CDATA ile birlikte çıkar
      const product = {
        xmlId: extractXMLValue(productXml, 'id'),
        stockCode: extractCDATAValue(productXml, 'stok_kodu'),
        barcode: extractCDATAValue(productXml, 'barkod'),
        categoryId: extractXMLValue(productXml, 'kategori_id'),
        categoryName: extractCDATAValue(productXml, 'kategori_ismi'),
        title: extractCDATAValue(productXml, 'urunismi'),
        subtitle: extractCDATAValue(productXml, 'alt_baslik'),
        description: extractCDATAValue(productXml, 'detayaciklama'),
        
        // Fiyat bilgileri - farklı formatları dene
        price: extractXMLValue(productXml, 'satisfiyati') || 
               extractXMLValue(productXml, 'fiyat') || 
               extractXMLValue(productXml, 'birimfiyat') ||
               extractCDATAValue(productXml, 'satisfiyati'),
               
        comparePrice: extractXMLValue(productXml, 'listeFiyati') || 
                     extractXMLValue(productXml, 'eskifiyat') ||
                     extractXMLValue(productXml, 'piyasafiyati'),
                     
        // Stok bilgileri - farklı formatları dene  
        stock: extractXMLValue(productXml, 'stok_adedi') || 
               extractXMLValue(productXml, 'stok') ||
               extractXMLValue(productXml, 'miktar') ||
               extractXMLValue(productXml, 'adet') || '0',
        weight: extractXMLValue(productXml, 'agirlik'),
        brand: extractCDATAValue(productXml, 'marka'),
        supplier: extractCDATAValue(productXml, 'tedarikci'),
        images: extractImageUrls(productXml),
        variants: extractVariants(productXml)
      };
      
      // Zorunlu alanlar kontrolü
      if (product.xmlId && product.title && !processedIds.has(product.xmlId)) {
        processedIds.add(product.xmlId);
        
        // Shopify formatına uygun hale getir
        product.shopifyTitle = product.title.length > 255 ? 
          product.title.substring(0, 252) + '...' : product.title;
        
        product.shopifyDescription = cleanDescription(product.description);
        product.shopifyPrice = parsePrice(product.price);
        product.shopifyComparePrice = parsePrice(product.comparePrice);
        product.shopifyStock = parseInt(product.stock) || 0;
        product.shopifyWeight = parseFloat(product.weight) || 0;
        
        // SKU oluştur (stok kodu veya XML ID)
        product.sku = product.stockCode || `XML_${product.xmlId}`;
        
        // Handle kategorisi
        product.productType = extractMainCategory(product.categoryName);
        product.tags = extractTags(product.categoryName, product.brand);
        
        products.push(product);
        
        // İlk 3 ürünün detaylarını logla
        if (products.length <= 3) {
          console.log(`📦 Ürün ${products.length} parse edildi:`, {
            id: product.xmlId,
            title: product.title?.substring(0, 50),
            price: product.shopifyPrice,
            stock: product.shopifyStock,
            images: product.images?.length || 0,
            variants: product.variants?.length || 0
          });
        }
      }
    } catch (error) {
      console.error(`⚠️ Ürün parse hatası (ID: ${extractXMLValue(productXml, 'id')}):`, error);
    }
  }
  
  console.log(`✓ ${products.length} benzersiz ürün başarıyla parse edildi`);
  return products;
}

// XML'den basit değer çıkar
function extractXMLValue(xml, tagName) {
  const regex = new RegExp(`<${tagName}>(.*?)<\/${tagName}>`, 'i');
  const match = xml.match(regex);
  return match ? match[1].trim() : null;
}

// CDATA değeri çıkar
function extractCDATAValue(xml, tagName) {
  const regex = new RegExp(`<${tagName}><!\\[CDATA\\[(.*?)\\]\\]><\/${tagName}>`, 'i');
  const match = xml.match(regex);
  return match ? match[1].trim() : extractXMLValue(xml, tagName);
}

// Resim URL'lerini çıkar - Sentos XML formatına göre
function extractImageUrls(productXml) {
  const images = [];
  
  // Farklı resim tag formatlarını dene
  const imagePatterns = [
    /<resim[^>]*><!\[CDATA\[(.*?)\]\]><\/resim>/gi,
    /<resim[^>]*>(.*?)<\/resim>/gi,
    /<image[^>]*><!\[CDATA\[(.*?)\]\]><\/image>/gi,
    /<image[^>]*>(.*?)<\/image>/gi,
    /<foto[^>]*><!\[CDATA\[(.*?)\]\]><\/foto>/gi,
    /<foto[^>]*>(.*?)<\/foto>/gi,
    /<gorsel[^>]*><!\[CDATA\[(.*?)\]\]><\/gorsel>/gi,
    /<gorsel[^>]*>(.*?)<\/gorsel>/gi
  ];
  
  imagePatterns.forEach(pattern => {
    let match;
    while ((match = pattern.exec(productXml))) {
      const imageUrl = match[1].trim();
      if (imageUrl && (imageUrl.startsWith('http') || imageUrl.startsWith('//'))) {
        // Protokol eksikse ekle
        const finalUrl = imageUrl.startsWith('//') ? 'https:' + imageUrl : imageUrl;
        if (!images.includes(finalUrl)) {
          images.push(finalUrl);
        }
      }
    }
  });
  
  console.log(`🖼️ ${images.length} resim bulundu`);
  return images;
}

// Varyantları çıkar (renk, beden vb.) - Sentos XML formatına göre
function extractVariants(productXml) {
  const variants = [];
  
  // Sentos XML'de varyantlar genelde aynı ürün ID'si ile farklı stok kodları olarak gelir
  // Bu fonksiyonu daha sonra geliştireceğiz, şimdilik temel bilgileri al
  
  const variant = {
    color: extractCDATAValue(productXml, 'renk') || extractXMLValue(productXml, 'renk'),
    size: extractCDATAValue(productXml, 'beden') || extractXMLValue(productXml, 'beden'),
    material: extractCDATAValue(productXml, 'malzeme') || extractXMLValue(productXml, 'malzeme'),
    pattern: extractCDATAValue(productXml, 'desen') || extractXMLValue(productXml, 'desen')
  };
  
  // En azından bir varyant özelliği varsa ekle
  if (variant.color || variant.size || variant.material || variant.pattern) {
    variants.push(variant);
  }
  
  // Eğer hiç varyant yoksa default bir varyant oluştur
  if (variants.length === 0) {
    variants.push({
      color: null,
      size: null,
      isDefault: true
    });
  }
  
  return variants;
}

// HTML temizle ve açıklama düzenle
function cleanDescription(description) {
  if (!description) return '';
  
  // HTML taglarını temizle
  let cleaned = description.replace(/<[^>]*>/g, '');
  
  // Fazla boşlukları temizle
  cleaned = cleaned.replace(/\s+/g, ' ').trim();
  
  // Shopify karakter sınırı (5000)
  if (cleaned.length > 5000) {
    cleaned = cleaned.substring(0, 4997) + '...';
  }
  
  return cleaned;
}

// Fiyat parse et
function parsePrice(priceStr) {
  if (!priceStr) return null;
  
  // Türkçe sayı formatını handle et (virgül ondalık ayırıcı)
  const cleanPrice = priceStr.replace(',', '.').replace(/[^\d.]/g, '');
  const price = parseFloat(cleanPrice);
  
  return isNaN(price) ? null : price.toFixed(2);
}

// Ana kategoriyi çıkar
function extractMainCategory(categoryPath) {
  if (!categoryPath) return 'Genel';
  
  // "Giyim > Büyük Beden > Alt Giyim > Pantolon" formatından "Giyim"
  const parts = categoryPath.split('>');
  return parts[0] ? parts[0].trim() : 'Genel';
}

// Etiketler oluştur
function extractTags(categoryPath, brand) {
  const tags = [];
  
  if (categoryPath) {
    const categoryParts = categoryPath.split('>').map(part => part.trim());
    tags.push(...categoryParts);
  }
  
  if (brand) {
    tags.push(brand);
  }
  
  // Boş ve duplicate'leri temizle
  return [...new Set(tags.filter(tag => tag && tag.length > 0))];
}

// Gelişmiş Shopify ürün listesi çekme
async function getShopifyProductsAdvanced(config) {
  console.log('🏪 Shopify ürünleri çekiliyor...');
  const products = [];
  let sinceId = 0;
  let hasMore = true;
  
  while (hasMore) {
    try {
      const url = `https://${config.storeUrl}/admin/api/2023-10/products.json?limit=250&since_id=${sinceId}`;
      const response = await fetch(url, {
        headers: { 
          'X-Shopify-Access-Token': config.accessToken,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error(`Shopify API error: ${response.status}`);
      }
      
      const data = await response.json();
      const fetchedProducts = data.products || [];
      
      if (fetchedProducts.length === 0) {
        hasMore = false;
      } else {
        products.push(...fetchedProducts);
        sinceId = fetchedProducts[fetchedProducts.length - 1].id;
        console.log(`📦 ${products.length} ürün çekildi...`);
        
        // Rate limiting için kısa bekle
        await new Promise(resolve => setTimeout(resolve, 250));
      }
    } catch (error) {
      console.error('❌ Shopify ürün çekme hatası:', error);
      hasMore = false;
    }
  }
  
  console.log(`✓ Toplam ${products.length} Shopify ürünü çekildi`);
  return products;
}

// Gelişmiş ürün senkronizasyonu
async function syncProductsAdvanced(xmlProducts, shopifyProducts, config) {
  const results = { 
    updated: 0, 
    created: 0, 
    skipped: 0, 
    errors: [],
    details: []
  };
  
  console.log(`⚡ ${xmlProducts.length} ürün senkronize edilecek...`);
  
  // Shopify ürünlerini SKU'ya göre indexle
  const shopifyBySku = new Map();
  const shopifyByTitle = new Map();
  
  shopifyProducts.forEach(product => {
    if (product.variants) {
      product.variants.forEach(variant => {
        if (variant.sku) {
          shopifyBySku.set(variant.sku, { product, variant });
        }
      });
    }
    
    if (product.title) {
      shopifyByTitle.set(product.title.toLowerCase().trim(), product);
    }
  });
  
  // XML ürünlerini işle - TÜM ürünleri gönder
  const productsToProcess = xmlProducts; // Artık tüm ürünleri işleyeceğiz
  
  console.log(`🚀 ${productsToProcess.length} ürün işlenecek...`);
  
  for (let i = 0; i < productsToProcess.length; i++) {
    const xmlProduct = productsToProcess[i];
    console.log(`🔄 İşleniyor (${i + 1}/${productsToProcess.length}): ${xmlProduct.title.substring(0, 50)}...`);
    
    try {
      // 1. SKU ile eşleşme ara
      let existingProduct = shopifyBySku.get(xmlProduct.sku);
      
      // 2. Bulamazsa title ile ara (fuzzy match)
      if (!existingProduct) {
        const titleKey = xmlProduct.title.toLowerCase().trim();
        existingProduct = shopifyByTitle.get(titleKey);
      }
      
      if (existingProduct) {
        // Mevcut ürünü güncelle
        const updateResult = await updateShopifyProductAdvanced(
          existingProduct.product || existingProduct, 
          xmlProduct, 
          config
        );
        
        if (updateResult.success) {
          results.updated++;
          results.details.push({
            action: 'updated',
            xmlId: xmlProduct.xmlId,
            shopifyId: (existingProduct.product || existingProduct).id,
            title: xmlProduct.title,
            changes: updateResult.changes
          });
          console.log(`✓ Güncellendi: ${xmlProduct.title.substring(0, 30)}...`);
        } else {
          results.skipped++;
          results.details.push({
            action: 'skipped',
            xmlId: xmlProduct.xmlId,
            title: xmlProduct.title,
            reason: updateResult.reason
          });
          console.log(`⏭️ Atlandı: ${xmlProduct.title.substring(0, 30)}... (${updateResult.reason})`);
        }
      } else {
        // Yeni ürün oluştur
        const createResult = await createShopifyProductAdvanced(xmlProduct, config);
        
        if (createResult.success) {
          results.created++;
          results.details.push({
            action: 'created',
            xmlId: xmlProduct.xmlId,
            shopifyId: createResult.productId,
            title: xmlProduct.title
          });
          console.log(`✨ Oluşturuldu: ${xmlProduct.title.substring(0, 30)}...`);
        } else {
          results.errors.push(`${xmlProduct.title}: ${createResult.error}`);
          console.log(`❌ Hata: ${xmlProduct.title.substring(0, 30)}... - ${createResult.error}`);
        }
      }
      
      // Rate limiting için bekle (Shopify API limitlerine uygun)
      await new Promise(resolve => setTimeout(resolve, 300));
      
    } catch (error) {
      results.errors.push(`${xmlProduct.title}: ${error.message}`);
      console.error(`❌ İşlem hatası: ${xmlProduct.title}`, error);
    }
  }
  
  console.log(`✅ Senkronizasyon tamamlandı: ${results.created} oluşturuldu, ${results.updated} güncellendi, ${results.skipped} atlandı, ${results.errors.length} hata`);
  return results;
}

// Gelişmiş Shopify ürün güncelleme
async function updateShopifyProductAdvanced(shopifyProduct, xmlProduct, config) {
  try {
    const changes = [];
    
    // Hangi alanların güncellenmesi gerektiğini kontrol et
    const updateData = { product: { id: shopifyProduct.id } };
    
    // Fiyat kontrolü
    if (xmlProduct.shopifyPrice && shopifyProduct.variants && shopifyProduct.variants[0]) {
      const currentPrice = parseFloat(shopifyProduct.variants[0].price);
      const newPrice = parseFloat(xmlProduct.shopifyPrice);
      
      if (Math.abs(currentPrice - newPrice) > 0.01) {
        changes.push(`Fiyat: ${currentPrice} → ${newPrice}`);
        updateData.product.variants = [{
          id: shopifyProduct.variants[0].id,
          price: xmlProduct.shopifyPrice,
          compare_at_price: xmlProduct.shopifyComparePrice,
          inventory_quantity: xmlProduct.shopifyStock,
          sku: xmlProduct.sku
        }];
      }
    }
    
    // Açıklama kontrolü
    if (xmlProduct.shopifyDescription && 
        xmlProduct.shopifyDescription !== shopifyProduct.body_html) {
      changes.push('Açıklama güncellendi');
      updateData.product.body_html = xmlProduct.shopifyDescription;
    }
    
    // Etiket kontrolü
    if (xmlProduct.tags && xmlProduct.tags.length > 0) {
      const currentTags = shopifyProduct.tags ? shopifyProduct.tags.split(',').map(t => t.trim()) : [];
      const newTags = xmlProduct.tags;
      
      if (JSON.stringify(currentTags.sort()) !== JSON.stringify(newTags.sort())) {
        changes.push('Etiketler güncellendi');
        updateData.product.tags = newTags.join(',');
      }
    }
    
    // Güncelleme gerekli mi?
    if (changes.length === 0) {
      return { success: true, changes: ['Değişiklik yok'], reason: 'no-changes' };
    }
    
    // Shopify'a güncelleme gönder
    const url = `https://${config.storeUrl}/admin/api/2023-10/products/${shopifyProduct.id}.json`;
    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'X-Shopify-Access-Token': config.accessToken,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(updateData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(`Shopify güncelleme hatası: ${JSON.stringify(errorData)}`);
    }
    
    return { success: true, changes };
    
  } catch (error) {
    return { success: false, reason: error.message };
  }
}

// Gelişmiş Shopify ürün oluşturma
async function createShopifyProductAdvanced(xmlProduct, config) {
  try {
    console.log(`🆕 Yeni ürün oluşturuluyor: ${xmlProduct.title.substring(0, 30)}...`);
    
    // Varyantları hazırla
    const variants = [];
    
    if (xmlProduct.variants && xmlProduct.variants.length > 0) {
      // XML'den gelen varyantları işle
      xmlProduct.variants.forEach((variant, index) => {
        variants.push({
          price: xmlProduct.shopifyPrice || '0.00',
          compare_at_price: xmlProduct.shopifyComparePrice,
          sku: xmlProduct.sku + (index > 0 ? `-${index}` : ''),
          inventory_quantity: Math.floor(xmlProduct.shopifyStock / xmlProduct.variants.length), // Stoku varyantlara böl
          weight: xmlProduct.shopifyWeight,
          weight_unit: 'kg',
          inventory_management: 'shopify',
          inventory_policy: 'deny',
          option1: variant.color || 'Standart',
          option2: variant.size,
          option3: variant.material
        });
      });
    } else {
      // Default varyant
      variants.push({
        price: xmlProduct.shopifyPrice || '0.00',
        compare_at_price: xmlProduct.shopifyComparePrice,
        sku: xmlProduct.sku,
        inventory_quantity: xmlProduct.shopifyStock,
        weight: xmlProduct.shopifyWeight,
        weight_unit: 'kg',
        inventory_management: 'shopify',
        inventory_policy: 'deny'
      });
    }
    
    // Ürün verisini hazırla
    const productData = {
      product: {
        title: xmlProduct.shopifyTitle,
        body_html: xmlProduct.shopifyDescription,
        vendor: xmlProduct.brand || 'XML Import',
        product_type: xmlProduct.productType,
        tags: xmlProduct.tags ? xmlProduct.tags.join(',') : '',
        variants: variants,
        images: xmlProduct.images && xmlProduct.images.length > 0 ? 
          xmlProduct.images.map(url => ({ src: url })) : []
      }
    };
    
    // Varyant seçeneklerini ayarla
    if (xmlProduct.variants && xmlProduct.variants.length > 0) {
      const hasColor = xmlProduct.variants.some(v => v.color);
      const hasSize = xmlProduct.variants.some(v => v.size);
      const hasMaterial = xmlProduct.variants.some(v => v.material);
      
      const options = [];
      if (hasColor) options.push({ name: 'Renk', position: 1 });
      if (hasSize) options.push({ name: 'Beden', position: 2 });
      if (hasMaterial) options.push({ name: 'Malzeme', position: 3 });
      
      if (options.length > 0) {
        productData.product.options = options;
      }
    }
    
    console.log(`📦 ${variants.length} varyant, ${productData.product.images.length} resim ile ürün oluşturuluyor...`);
    
    const url = `https://${config.storeUrl}/admin/api/2023-10/products.json`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-Shopify-Access-Token': config.accessToken,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(productData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      console.error('❌ Shopify oluşturma hatası:', errorData);
      throw new Error(`Shopify oluşturma hatası: ${JSON.stringify(errorData)}`);
    }
    
    const result = await response.json();
    console.log(`✅ Ürün oluşturuldu - Shopify ID: ${result.product.id}`);
    return { success: true, productId: result.product.id };
    
  } catch (error) {
    console.error(`❌ Ürün oluşturma hatası: ${xmlProduct.title}`, error);
    return { success: false, error: error.message };
  }
}
