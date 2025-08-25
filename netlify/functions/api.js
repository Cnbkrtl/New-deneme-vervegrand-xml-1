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
    const response = await fetch(xmlUrl);
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlText = await response.text();
    
    // XML analizi - gerçek ürün sayısını bul
    const analysis = analyzeXML(xmlText);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        status: 'success', 
        data: {
          products: analysis.products,
          uniqueProducts: analysis.uniqueProducts,
          duplicateCount: analysis.duplicateCount,
          structure: analysis.structure,
          sampleProducts: analysis.sampleProducts,
          xmlInfo: analysis.xmlInfo,
          lastUpdated: new Date().toISOString(),
          connected: true,
          healthy: analysis.products > 0
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

// XML analiz fonksiyonu - debug sonuçlarına göre optimize edildi
function analyzeXML(xmlText) {
  console.log('XML Preview:', xmlText.substring(0, 1000));
  
  // XML'deki <Urun> etiketlerini say (debug sonuçlarına göre)
  const urunCount = (xmlText.match(/<Urun[\s>]/gi) || []).length;
  
  // Benzersiz ürünleri tespit et
  const uniqueProducts = new Set();
  const uniqueStockCodes = new Set();
  const duplicateProducts = [];
  
  // Örnek ürün bilgilerini çıkar ve duplicate kontrolü yap
  const sampleProducts = [];
  const urunRegex = /<Urun[\s>][\s\S]*?<\/Urun>/gi;
  let match;
  let sampleCount = 0;
  let processedCount = 0;
  
  while ((match = urunRegex.exec(xmlText))) {
    const productXml = match[0];
    processedCount++;
    
    // Ürün bilgilerini çıkar
    const getId = (xml) => {
      const idMatch = xml.match(/<id>(.*?)<\/id>/i);
      return idMatch ? idMatch[1].trim() : null;
    };
    
    const getStokKodu = (xml) => {
      const stokMatch = xml.match(/<stok_kodu><!\[CDATA\[(.*?)\]\]><\/stok_kodu>/i);
      return stokMatch ? stokMatch[1].trim() : null;
    };
    
    const getUrunIsmi = (xml) => {
      const isimMatch = xml.match(/<urunismi><!\[CDATA\[(.*?)\]\]><\/urunismi>/i);
      return isimMatch ? isimMatch[1].trim() : null;
    };
    
    const getKategori = (xml) => {
      const kategoriMatch = xml.match(/<kategori_ismi><!\[CDATA\[(.*?)\]\]><\/kategori_ismi>/i);
      return kategoriMatch ? kategoriMatch[1].trim() : null;
    };
    
    const productId = getId(productXml);
    const stokKodu = getStokKodu(productXml);
    const urunIsmi = getUrunIsmi(productXml);
    const kategori = getKategori(productXml);
    
    // Benzersiz ürün kontrolü (ID ve stok kodu ile)
    const uniqueKey = `${productId}_${stokKodu}`;
    
    if (productId && !uniqueProducts.has(productId)) {
      uniqueProducts.add(productId);
      
      if (stokKodu && !uniqueStockCodes.has(stokKodu)) {
        uniqueStockCodes.add(stokKodu);
      }
      
      // İlk 5 benzersiz ürünü örnek olarak al
      if (sampleCount < 5) {
        sampleProducts.push({
          id: productId,
          stokKodu: stokKodu || 'N/A',
          urunIsmi: urunIsmi || 'N/A',
          kategori: kategori || 'N/A'
        });
        sampleCount++;
      }
    } else if (productId && uniqueProducts.has(productId)) {
      // Duplicate ürün bulundu
      duplicateProducts.push({
        id: productId,
        stokKodu: stokKodu,
        position: processedCount
      });
    }
  }
  
  return {
    products: urunCount, // Toplam XML'deki ürün sayısı
    uniqueProducts: uniqueProducts.size, // Benzersiz ürün sayısı (ID'ye göre)
    uniqueStockCodes: uniqueStockCodes.size, // Benzersiz stok kodu sayısı
    duplicateCount: duplicateProducts.length, // Duplicate ürün sayısı
    structure: 'Urunler/Urun', // Debug sonuçlarına göre
    sampleProducts: sampleProducts,
    duplicateExamples: duplicateProducts.slice(0, 5), // İlk 5 duplicate örneği
    xmlInfo: {
      totalSize: xmlText.length,
      hasStockCodes: xmlText.includes('<stok_kodu>'),
      hasCDATA: xmlText.includes('<![CDATA['),
      hasCategories: xmlText.includes('<kategori_ismi>'),
      encoding: xmlText.includes('utf-8') ? 'UTF-8' : 'Unknown'
    },
    analysis: {
      totalProcessed: processedCount,
      duplicateRatio: ((duplicateProducts.length / urunCount) * 100).toFixed(1) + '%',
      uniqueRatio: ((uniqueProducts.size / urunCount) * 100).toFixed(1) + '%'
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
    // Ayarları localStorage'dan al (gerçek implementasyonda body'den gelir)
    const xmlUrl = 'https://stildiva.sentos.com.tr/xml-sentos-out/1'; // Örnek
    const shopifyConfig = {
      storeUrl: 'c1grp2-yr.myshopify.com',
      accessToken: 'şifre' // Gerçek token gerekli
    };
    
    // 1. XML'i çek ve analiz et
    const xmlResponse = await fetch(xmlUrl);
    const xmlText = await xmlResponse.text();
    const xmlAnalysis = analyzeXML(xmlText);
    
    // 2. XML'den ürün verilerini çıkar
    const xmlProducts = parseXMLProducts(xmlText);
    
    // 3. Shopify'daki mevcut ürünleri kontrol et
    const shopifyProducts = await getShopifyProducts(shopifyConfig);
    
    // 4. Senkronizasyon işlemini yap
    const syncResults = await syncProducts(xmlProducts, shopifyProducts, shopifyConfig);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          xmlProductsFound: xmlAnalysis.products,
          shopifyProductsExisting: shopifyProducts.length,
          productsUpdated: syncResults.updated,
          productsCreated: syncResults.created,
          errors: syncResults.errors
        }
      })
    };
  } catch (error) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

// XML'den ürün bilgilerini çıkar
function parseXMLProducts(xmlText) {
  const products = [];
  // Basit regex ile ürün bilgilerini çıkar
  const productMatches = xmlText.match(/<urun[^>]*>[\s\S]*?<\/urun>/gi) || [];
  
  productMatches.forEach(productXML => {
    const product = {
      id: extractValue(productXML, 'id'),
      title: extractValue(productXML, 'baslik') || extractValue(productXML, 'name'),
      price: extractValue(productXML, 'fiyat') || extractValue(productXML, 'price'),
      stock: extractValue(productXML, 'stok') || extractValue(productXML, 'stock'),
      description: extractValue(productXML, 'aciklama') || extractValue(productXML, 'description')
    };
    if (product.id && product.title) {
      products.push(product);
    }
  });
  
  return products;
}

// XML'den değer çıkar
function extractValue(xml, tagName) {
  const regex = new RegExp(`<${tagName}[^>]*>([^<]*)<\/${tagName}>`, 'i');
  const match = xml.match(regex);
  return match ? match[1].trim() : null;
}

// Shopify'dan ürünleri çek
async function getShopifyProducts(config) {
  const url = `https://${config.storeUrl}/admin/api/2023-01/products.json?limit=250`;
  const response = await fetch(url, {
    headers: { 'X-Shopify-Access-Token': config.accessToken }
  });
  const data = await response.json();
  return data.products || [];
}

// Ürün senkronizasyonu
async function syncProducts(xmlProducts, shopifyProducts, config) {
  const results = { updated: 0, created: 0, errors: [] };
  
  for (const xmlProduct of xmlProducts.slice(0, 5)) { // İlk 5 ürünle test
    try {
      const existingProduct = shopifyProducts.find(p => p.title === xmlProduct.title);
      
      if (existingProduct) {
        // Mevcut ürünü güncelle
        await updateShopifyProduct(existingProduct.id, xmlProduct, config);
        results.updated++;
      } else {
        // Yeni ürün oluştur
        await createShopifyProduct(xmlProduct, config);
        results.created++;
      }
    } catch (error) {
      results.errors.push(`${xmlProduct.title}: ${error.message}`);
    }
  }
  
  return results;
}

// Shopify ürün güncelle
async function updateShopifyProduct(productId, xmlProduct, config) {
  const url = `https://${config.storeUrl}/admin/api/2023-01/products/${productId}.json`;
  const updateData = {
    product: {
      id: productId,
      variants: [{
        price: xmlProduct.price,
        inventory_quantity: parseInt(xmlProduct.stock) || 0
      }]
    }
  };
  
  await fetch(url, {
    method: 'PUT',
    headers: {
      'X-Shopify-Access-Token': config.accessToken,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(updateData)
  });
}

// Shopify'da yeni ürün oluştur
async function createShopifyProduct(xmlProduct, config) {
  const url = `https://${config.storeUrl}/admin/api/2023-01/products.json`;
  const productData = {
    product: {
      title: xmlProduct.title,
      body_html: xmlProduct.description,
      vendor: 'XML Import',
      product_type: 'General',
      variants: [{
        price: xmlProduct.price,
        inventory_quantity: parseInt(xmlProduct.stock) || 0,
        inventory_management: 'shopify'
      }]
    }
  };
  
  await fetch(url, {
    method: 'POST',
    headers: {
      'X-Shopify-Access-Token': config.accessToken,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(productData)
  });
}
