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
          productCount: analysis.products,
          variantCount: analysis.variants,
          xmlSize: xmlText.length,
          lastUpdated: new Date().toISOString(),
          connected: true,
          healthy: analysis.products > 0,
          structure: analysis.structure
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

// XML analiz fonksiyonu
function analyzeXML(xmlText) {
  // Önce XML yapısını incele
  console.log('XML Preview:', xmlText.substring(0, 1000));
  
  // Benzersiz ürün ID'lerini bul
  const uniqueProducts = new Set();
  
  // Farklı ürün ID pattern'lerini dene
  const idPatterns = [
    /<urun[^>]*id="([^"]+)"/gi,           // <urun id="123">
    /<urun[^>]*><id>([^<]+)<\/id>/gi,     // <urun><id>123</id>
    /<product[^>]*id="([^"]+)"/gi,        // <product id="123">
    /<item[^>]*id="([^"]+)"/gi,           // <item id="123">
    /<urun[^>]*><kod>([^<]+)<\/kod>/gi,   // <urun><kod>123</kod>
  ];
  
  for (const pattern of idPatterns) {
    let match;
    while ((match = pattern.exec(xmlText)) !== null) {
      uniqueProducts.add(match[1]);
    }
  }
  
  // Eğer ID bulunamazsa, benzersiz ürün başlıklarını say
  if (uniqueProducts.size === 0) {
    const titlePatterns = [
      /<baslik>([^<]+)<\/baslik>/gi,
      /<name>([^<]+)<\/name>/gi,
      /<title>([^<]+)<\/title>/gi
    ];
    
    for (const pattern of titlePatterns) {
      let match;
      while ((match = pattern.exec(xmlText)) !== null) {
        uniqueProducts.add(match[1]);
      }
    }
  }
  
  // Son çare: ürün taglarını say ama benzersiz olanları
  let productCount = uniqueProducts.size;
  if (productCount === 0) {
    const urunTags = xmlText.match(/<urun[^>]*>/gi) || [];
    productCount = urunTags.length;
  }
  
  // Varyant analizi
  const variantCount = (xmlText.match(/<varyant[^>]*>/gi) || []).length + 
                      (xmlText.match(/<variant[^>]*>/gi) || []).length;
  
  return {
    products: productCount,
    variants: variantCount,
    structure: 'urun', // Sentos XML yapısı
    uniqueIds: uniqueProducts.size,
    debug: {
      urunTags: (xmlText.match(/<urun[^>]*>/gi) || []).length,
      productTags: (xmlText.match(/<product[^>]*>/gi) || []).length,
      itemTags: (xmlText.match(/<item[^>]*>/gi) || []).length
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
