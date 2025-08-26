// Chunked processing için yardımcı endpoint
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
  
  if (path.endsWith('/xml-fast')) {
    return handleXMLFast(event, headers);
  }
  if (path.endsWith('/sync-batch')) {
    return handleSyncBatch(event, headers);
  }
  
  return {
    statusCode: 404,
    headers,
    body: JSON.stringify({ error: 'Endpoint not found' })
  };
};

// Ultra hızlı XML analizi - sadece sayıları döndürür
async function handleXMLFast(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  const { xmlUrl } = JSON.parse(event.body);

  try {
    console.log('⚡ Ultra hızlı XML analizi başlıyor...');
    
    // Sadece ilk 100KB'ı çek - sample için
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 saniye
    
    const response = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'Range': 'bytes=0-102400', // İlk 100KB
        'User-Agent': 'XML-Fast-Analyzer/1.0'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlSample = await response.text();
    
    // Hızlı pattern matching
    const urunMatches = xmlSample.match(/<Urun[\s>]/gi) || [];
    const estimatedProducts = urunMatches.length * 10; // Tahminî toplam
    
    // İlk ürün bilgisi
    const firstUrun = xmlSample.match(/<Urun[\s>][\s\S]*?(?:<\/Urun>|$)/i);
    let sampleProduct = null;
    
    if (firstUrun) {
      const urunXml = firstUrun[0];
      sampleProduct = {
        stokKodu: (urunXml.match(/<StokKodu><!\[CDATA\[(.*?)\]\]><\/StokKodu>/i) || ['', 'N/A'])[1],
        urunAdi: (urunXml.match(/<UrunAdi><!\[CDATA\[(.*?)\]\]><\/UrunAdi>/i) || ['', 'N/A'])[1],
        fiyat: (urunXml.match(/<SatisFiyati1>(.*?)<\/SatisFiyati1>/i) || ['', '0'])[1]
      };
    }
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          estimatedProducts,
          sampleSize: xmlSample.length,
          sampleProduct,
          method: 'fast-analysis',
          timestamp: new Date().toISOString()
        }
      })
    };
    
  } catch (error) {
    console.error('❌ Fast XML error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

// Batch sync - tüm ürünleri işle + Shopify entegrasyonu
async function handleSyncBatch(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const { xmlUrl, storeUrl, accessToken, apiKey } = JSON.parse(event.body);
    
    console.log(`⚡ Full batch sync başlıyor (tüm ürünler)...`);
    const startTime = Date.now();
    
    // 1. Tüm XML'i çek (büyük dosyalar için chunked)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000); // 25 saniye
    
    const response = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Full-Batch-Sync/1.0',
        'Accept-Encoding': 'gzip, deflate'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlText = await response.text();
    const xmlSizeMB = xmlText.length / 1024 / 1024;
    console.log(`✓ XML çekildi: ${xmlSizeMB.toFixed(2)}MB`);
    
    // 2. Tüm ürünleri parse et
    const urunMatches = xmlText.match(/<Urun[\s>][\s\S]*?<\/Urun>/gi) || [];
    console.log(`✓ ${urunMatches.length} ürün bulundu`);
    
    const products = [];
    for (const urunXml of urunMatches) {
      try {
        const product = parseUrunXMLAdvanced(urunXml);
        if (product && product.stokKodu) {
          products.push(product);
        }
      } catch (parseError) {
        console.warn('Parse error:', parseError.message);
      }
    }
    
    console.log(`✓ ${products.length} ürün başarıyla parse edildi`);
    
    // 3. Shopify'daki mevcut ürünleri çek
    console.log('🏪 Shopify ürünleri kontrol ediliyor...');
    const shopifyProducts = await getShopifyProducts(storeUrl, accessToken);
    console.log(`✓ Shopify'da ${shopifyProducts.length} ürün bulundu`);
    
    // 4. Eşleşme ve sync işlemi
    const syncResults = {
      created: 0,
      updated: 0, 
      skipped: 0,
      errors: [],
      details: {
        skuMatches: 0,
        titleMatches: 0,
        newProducts: 0,
        duplicates: 0
      }
    };
    
    // Benzersiz ürünleri filtrele
    const uniqueProducts = [];
    const seenSKUs = new Set();
    
    for (const product of products) {
      if (!seenSKUs.has(product.stokKodu)) {
        seenSKUs.add(product.stokKodu);
        uniqueProducts.push(product);
      } else {
        syncResults.details.duplicates++;
      }
    }
    
    console.log(`✓ ${uniqueProducts.length} benzersiz ürün (${syncResults.details.duplicates} duplicate)`);
    
    // 5. Her ürün için eşleşme kontrolü ve sync
    for (const product of uniqueProducts) {
      try {
        // SKU ile eşleşme kontrolü
        let existingProduct = shopifyProducts.find(sp => 
          sp.variants && sp.variants.some(v => v.sku === product.stokKodu)
        );
        
        let matchType = '';
        
        if (existingProduct) {
          matchType = 'sku';
          syncResults.details.skuMatches++;
        } else {
          // Title ile eşleşme kontrolü (%80+ benzerlik)
          existingProduct = shopifyProducts.find(sp => 
            calculateSimilarity(sp.title, product.urunAdi) > 0.8
          );
          
          if (existingProduct) {
            matchType = 'title';
            syncResults.details.titleMatches++;
          }
        }
        
        if (existingProduct) {
          // Güncelleme
          const updateResult = await updateShopifyProduct(existingProduct, product, storeUrl, accessToken);
          if (updateResult.success) {
            syncResults.updated++;
          } else {
            syncResults.errors.push(`${product.stokKodu}: Update failed - ${updateResult.error}`);
          }
        } else {
          // Yeni ürün oluştur
          const createResult = await createShopifyProduct(product, storeUrl, accessToken);
          if (createResult.success) {
            syncResults.created++;
            syncResults.details.newProducts++;
          } else {
            syncResults.errors.push(`${product.stokKodu}: Create failed - ${createResult.error}`);
          }
        }
        
        // Rate limiting için kısa bekleme
        await new Promise(resolve => setTimeout(resolve, 100));
        
      } catch (productError) {
        syncResults.errors.push(`${product.stokKodu}: ${productError.message}`);
      }
    }
    
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    
    console.log(`✅ Full batch sync tamamlandı (${duration}s)`);
    console.log(`📊 Sonuç: ${syncResults.created} created, ${syncResults.updated} updated, ${syncResults.errors.length} errors`);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          xmlProductsFound: urunMatches.length,
          uniqueProducts: uniqueProducts.length,
          productsCreated: syncResults.created,
          productsUpdated: syncResults.updated,
          productsSkipped: syncResults.details.duplicates,
          errors: syncResults.errors,
          duration: duration + 's',
          timestamp: new Date().toISOString(),
          details: {
            xmlSize: xmlSizeMB.toFixed(2) + 'MB',
            skuMatches: syncResults.details.skuMatches,
            titleMatches: syncResults.details.titleMatches,
            newProducts: syncResults.details.newProducts,
            duplicates: syncResults.details.duplicates,
            successRate: ((syncResults.created + syncResults.updated) / uniqueProducts.length * 100).toFixed(1) + '%'
          }
        }
      })
    };
    
  } catch (error) {
    console.error('❌ Full batch sync error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ 
        status: 'error', 
        error: error.message,
        method: 'full-batch-sync'
      })
    };
  }
}

// Shopify ürünlerini çek
async function getShopifyProducts(storeUrl, accessToken) {
  try {
    const response = await fetch(`${storeUrl}/admin/api/2023-10/products.json?limit=250`, {
      headers: {
        'X-Shopify-Access-Token': accessToken,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) throw new Error(`Shopify API error: ${response.status}`);
    
    const data = await response.json();
    return data.products || [];
  } catch (error) {
    console.error('Shopify products fetch error:', error);
    return [];
  }
}

// String benzerlik hesaplama
function calculateSimilarity(str1, str2) {
  if (!str1 || !str2) return 0;
  
  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;
  
  if (longer.length === 0) return 1.0;
  
  const distance = levenshteinDistance(longer.toLowerCase(), shorter.toLowerCase());
  return (longer.length - distance) / longer.length;
}

function levenshteinDistance(str1, str2) {
  const matrix = [];
  
  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }
  
  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }
  
  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  
  return matrix[str2.length][str1.length];
}

// Shopify ürün güncelle
async function updateShopifyProduct(existingProduct, xmlProduct, storeUrl, accessToken) {
  try {
    const updatedProduct = {
      id: existingProduct.id,
      title: xmlProduct.urunAdi,
      body_html: xmlProduct.aciklama || '',
      variants: existingProduct.variants.map(variant => ({
        ...variant,
        price: xmlProduct.fiyat,
        inventory_quantity: xmlProduct.stok
      }))
    };
    
    const response = await fetch(`${storeUrl}/admin/api/2023-10/products/${existingProduct.id}.json`, {
      method: 'PUT',
      headers: {
        'X-Shopify-Access-Token': accessToken,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ product: updatedProduct })
    });
    
    if (response.ok) {
      return { success: true };
    } else {
      const errorText = await response.text();
      return { success: false, error: errorText.substring(0, 100) };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Shopify ürün oluştur
async function createShopifyProduct(xmlProduct, storeUrl, accessToken) {
  try {
    const newProduct = {
      title: xmlProduct.urunAdi,
      body_html: xmlProduct.aciklama || '',
      vendor: 'XML Import',
      product_type: xmlProduct.kategori || 'General',
      status: 'active',
      tags: xmlProduct.kategori ? [xmlProduct.kategori] : [],
      variants: [{
        price: xmlProduct.fiyat,
        sku: xmlProduct.stokKodu,
        inventory_quantity: xmlProduct.stok,
        barcode: xmlProduct.barkod || '',
        weight: 0,
        weight_unit: 'kg'
      }]
    };
    
    const response = await fetch(`${storeUrl}/admin/api/2023-10/products.json`, {
      method: 'POST',
      headers: {
        'X-Shopify-Access-Token': accessToken,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ product: newProduct })
    });
    
    if (response.ok) {
      return { success: true };
    } else {
      const errorText = await response.text();
      return { success: false, error: errorText.substring(0, 100) };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Gelişmiş ürün parse fonksiyonu
function parseUrunXMLAdvanced(urunXml) {
  try {
    const extractCDATA = (str, tag) => {
      const match = str.match(new RegExp(`<${tag}><!\\[CDATA\\[(.*?)\\]\\]></${tag}>`, 'i'));
      return match ? match[1].trim() : null;
    };
    
    const extractValue = (str, tag) => {
      const match = str.match(new RegExp(`<${tag}>(.*?)</${tag}>`, 'i'));
      return match ? match[1].trim() : null;
    };
    
    return {
      stokKodu: extractCDATA(urunXml, 'StokKodu'),
      urunAdi: extractCDATA(urunXml, 'UrunAdi'),
      aciklama: extractCDATA(urunXml, 'Aciklama'),
      fiyat: parseFloat(extractValue(urunXml, 'SatisFiyati1')) || 0,
      stok: parseInt(extractValue(urunXml, 'StokMiktari')) || 0,
      kategori: extractCDATA(urunXml, 'UrunGrubu'),
      barkod: extractCDATA(urunXml, 'Barkod')
    };
  } catch (error) {
    return null;
  }
}
