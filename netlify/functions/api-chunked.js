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

// Batch sync - az sayıda ürünle + Shopify entegrasyonu
async function handleSyncBatch(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const { xmlUrl, storeUrl, accessToken, apiKey, maxProducts = 3 } = JSON.parse(event.body);
    
    console.log(`⚡ Batch sync başlıyor (max ${maxProducts} ürün)...`);
    const startTime = Date.now();
    
    // 1. XML'den sadece ilk birkaç ürünü çek (ultra hızlı)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 saniye
    
    const response = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'Range': 'bytes=0-524288', // İlk 512KB
        'User-Agent': 'Batch-Sync/1.0'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlChunk = await response.text();
    console.log(`✓ XML chunk çekildi: ${(xmlChunk.length / 1024).toFixed(0)}KB`);
    
    // 2. Sadece ilk N ürünü parse et
    const urunMatches = xmlChunk.match(/<Urun[\s>][\s\S]*?<\/Urun>/gi) || [];
    const limitedUrunlar = urunMatches.slice(0, maxProducts);
    
    const products = [];
    for (const urunXml of limitedUrunlar) {
      try {
        const product = parseUrunXMLAdvanced(urunXml);
        if (product && product.stokKodu) {
          products.push(product);
        }
      } catch (parseError) {
        console.warn('Parse error:', parseError.message);
      }
    }
    
    console.log(`✓ ${products.length} ürün parse edildi`);
    
    // 3. Shopify'a hızlı gönder (sadece temel bilgiler)
    let created = 0, updated = 0, errors = [];
    
    for (const product of products) {
      try {
        const shopifyProduct = {
          title: product.urunAdi,
          body_html: product.aciklama || '',
          vendor: 'XML Import',
          product_type: 'General',
          status: 'active',
          variants: [{
            price: product.fiyat,
            sku: product.stokKodu,
            inventory_quantity: product.stok,
            weight: 0
          }]
        };
        
        // Shopify'a POST et (sadece create, update yapmayalım - hızlı olsun)
        const shopifyResponse = await fetch(`${storeUrl}/admin/api/2023-10/products.json`, {
          method: 'POST',
          headers: {
            'X-Shopify-Access-Token': accessToken,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ product: shopifyProduct })
        });
        
        if (shopifyResponse.ok) {
          created++;
        } else {
          const errorText = await shopifyResponse.text();
          errors.push(`${product.stokKodu}: ${errorText.substring(0, 100)}`);
        }
        
      } catch (productError) {
        errors.push(`${product.stokKodu}: ${productError.message}`);
      }
      
      // Her üründen sonra kısa bekleme
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    
    console.log(`✅ Batch sync tamamlandı (${duration}s): ${created} created, ${errors.length} errors`);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          productsProcessed: products.length,
          productsCreated: created,
          productsUpdated: 0,
          productsSkipped: 0,
          errors: errors,
          duration: duration + 's',
          method: 'batch-sync',
          timestamp: new Date().toISOString(),
          details: {
            xmlChunkSize: xmlChunk.length,
            totalFound: urunMatches.length,
            processed: products.slice(0, 2) // İlk 2 ürünün detayı
          }
        }
      })
    };
    
  } catch (error) {
    console.error('❌ Batch sync error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ 
        status: 'error', 
        error: error.message,
        method: 'batch-sync'
      })
    };
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

// Basit ürün parse fonksiyonu
function parseUrunXML(urunXml) {
  try {
    return {
      stokKodu: (urunXml.match(/<StokKodu><!\[CDATA\[(.*?)\]\]><\/StokKodu>/i) || ['', null])[1],
      urunAdi: (urunXml.match(/<UrunAdi><!\[CDATA\[(.*?)\]\]><\/UrunAdi>/i) || ['', null])[1],
      fiyat: parseFloat((urunXml.match(/<SatisFiyati1>(.*?)<\/SatisFiyati1>/i) || ['', '0'])[1]) || 0,
      stok: parseInt((urunXml.match(/<StokMiktari>(.*?)<\/StokMiktari>/i) || ['', '0'])[1]) || 0
    };
  } catch (error) {
    return null;
  }
}
