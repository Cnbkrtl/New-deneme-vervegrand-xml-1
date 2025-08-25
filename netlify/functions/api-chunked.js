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

// Batch sync - az sayıda ürünle
async function handleSyncBatch(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const { xmlUrl, shopifyUrl, shopifyToken, apiKey, maxProducts = 5 } = JSON.parse(event.body);
    
    console.log(`⚡ Batch sync başlıyor (max ${maxProducts} ürün)...`);
    
    // Sadece küçük chunk'ı işle
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000); // 20 saniye
    
    const response = await fetch(xmlUrl, {
      signal: controller.signal,
      headers: {
        'Range': 'bytes=0-1048576', // İlk 1MB
        'User-Agent': 'Batch-Sync/1.0'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) throw new Error(`XML fetch error: ${response.status}`);
    
    const xmlChunk = await response.text();
    
    // Sadece ilk N ürünü çıkar
    const urunMatches = xmlChunk.match(/<Urun[\s>][\s\S]*?<\/Urun>/gi) || [];
    const limitedUrunlar = urunMatches.slice(0, maxProducts);
    
    const products = [];
    for (const urunXml of limitedUrunlar) {
      try {
        const product = parseUrunXML(urunXml);
        if (product) products.push(product);
      } catch (parseError) {
        console.warn('Parse error:', parseError.message);
      }
    }
    
    console.log(`✓ ${products.length} ürün batch'te işlendi`);
    
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        status: 'success',
        data: {
          productsProcessed: products.length,
          products: products.slice(0, 3), // Sadece ilk 3'ünü döndür
          totalFound: urunMatches.length,
          method: 'batch-sync',
          timestamp: new Date().toISOString()
        }
      })
    };
    
  } catch (error) {
    console.error('❌ Batch sync error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
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
