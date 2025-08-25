import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const navigate = useNavigate();
  const [connectionStatus, setConnectionStatus] = useState({
    shopify: { status: 'pending', data: {} },
    xml: { status: 'pending', data: {} },
    google: { status: 'pending', data: {} }
  });
  const [syncStatus, setSyncStatus] = useState('idle');
  const [syncDetails, setSyncDetails] = useState(null);
  const [fastMode, setFastMode] = useState(false);

  // Sayfa yüklendiğinde otomatik bağlantı testi yap
  useEffect(() => {
    testConnections();
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    navigate('/login');
  };

  const testConnections = async () => {
    const testEndpoint = async (endpoint, key) => {
      setConnectionStatus(prev => ({ ...prev, [key]: { status: 'testing', data: {} } }));
      try {
        let body = {};
        
        if (key === 'shopify') {
          body = {
            apiKey: localStorage.getItem('shopify_api_key'),
            apiSecret: localStorage.getItem('shopify_api_secret'),
            storeUrl: localStorage.getItem('shopify_store_url'),
            accessToken: localStorage.getItem('shopify_access_token')
          };
        } else if (key === 'xml') {
          body = { xmlUrl: localStorage.getItem('xml_url') };
        } else if (key === 'google') {
          body = {
            clientId: localStorage.getItem('google_client_id'),
            apiKey: localStorage.getItem('google_api_key'),
            spreadsheetId: localStorage.getItem('google_spreadsheet_id')
          };
        }

        // XML için özel timeout ayarı
        const timeoutMs = key === 'xml' ? 60000 : 10000; // XML için 60 saniye
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        
        const response = await fetch(`/api${fastMode && key === 'xml' ? '-chunked' : ''}/${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`${response.status}: ${errorText}`);
        }
        const data = await response.json();
        setConnectionStatus(prev => ({ ...prev, [key]: { status: 'connected', data: data.data || {} } }));
      } catch (error) {
        console.error(`Error testing ${key}:`, error);
        let errorMessage = error.message;
        
        // Timeout hatası için özel mesaj
        if (error.name === 'AbortError') {
          errorMessage = `${key.toUpperCase()} bağlantısı zaman aşımına uğradı (${timeoutMs/1000}s)`;
        }
        
        setConnectionStatus(prev => ({ 
          ...prev, 
          [key]: { 
            status: 'failed', 
            data: {}, 
            error: errorMessage 
          } 
        }));
      }
    };

    await Promise.all([
      testEndpoint('shopify', 'shopify'),
      testEndpoint('xml', fastMode ? 'xml-fast' : 'xml'),
      testEndpoint('google', 'google')
    ]);
  };

  const startSync = async () => {
    setSyncStatus('running');
    setSyncDetails(null);
    
    try {
      // API bilgilerini localStorage'dan al ve kontrol et
      const xmlUrl = localStorage.getItem('xml_url');
      const storeUrl = localStorage.getItem('shopify_store_url');
      const accessToken = localStorage.getItem('shopify_access_token');
      const apiKey = localStorage.getItem('shopify_api_key');
      
      console.log('📥 Sync Request Data:', {
        xmlUrl: xmlUrl ? 'OK' : 'MISSING',
        storeUrl: storeUrl ? 'OK' : 'MISSING',
        accessToken: accessToken ? 'OK' : 'MISSING',
        apiKey: apiKey ? 'OK' : 'MISSING'
      });
      
      // Gerekli bilgileri kontrol et
      if (!xmlUrl) {
        throw new Error('XML URL ayarlanmamış. Lütfen Settings sayfasından XML URL\'ini girin.');
      }
      if (!storeUrl || !accessToken) {
        throw new Error('Shopify API bilgileri eksik. Lütfen Settings sayfasından Shopify ayarlarını tamamlayın.');
      }
      
      const syncRequest = {
        xmlUrl,
        storeUrl,
        accessToken,
        apiKey
      };
      
      console.log('🚀 Senkronizasyon isteği gönderiliyor...');
      
      // Sync için chunked API kullan (daha hızlı)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000);
      
      const syncEndpoint = fastMode ? '/api-chunked/sync-batch' : '/api/sync';
      console.log(`🎯 Sync endpoint: ${syncEndpoint}`);
      
      const response = await fetch(syncEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(syncRequest),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      console.log('📡 Response status:', response.status);
      
      if (!response.ok) {
        let errorText;
        try {
          errorText = await response.text();
        } catch (parseError) {
          errorText = `HTTP ${response.status} - Response parse error`;
        }
        console.error('❌ Sync response error:', errorText);
        throw new Error(`Sync failed (${response.status}): ${errorText}`);
      }
      
      let data;
      try {
        data = await response.json();
      } catch (jsonError) {
        console.error('❌ JSON parse error:', jsonError);
        throw new Error('Sync response format error - invalid JSON');
      }
      
      setSyncStatus('completed');
      setSyncDetails(data.data);
      
      // Detaylı sonuç göster
      const summary = `
🎉 Senkronizasyon Tamamlandı!

📊 Özet:
• ${data.data.productsCreated} yeni ürün eklendi
• ${data.data.productsUpdated} ürün güncellendi  
• ${data.data.productsSkipped} ürün atlandı
• ${data.data.errors.length} hata oluştu

⏱️ Süre: ${data.data.duration}
📅 Tarih: ${new Date(data.data.timestamp).toLocaleString('tr-TR')}
      `;
      
      alert(summary);
    } catch (error) {
      setSyncStatus('failed');
      
      console.error('🚨 Sync Error Details:', {
        name: error.name,
        message: error.message,
        stack: error.stack
      });
      
      let errorMessage = error.message;
      let errorDetails = '';
      
      if (error.name === 'AbortError') {
        errorMessage = fastMode ? 
          'Hızlı mod sync zaman aşımına uğradı (60 saniye)' :
          'Senkronizasyon zaman aşımına uğradı (60 saniye)';
        errorDetails = `
🚨 Zaman Aşımı Sorunu:
• ${fastMode ? 'Hızlı mod bile timeout aldı - XML çok büyük' : 'XML dosyası çok büyük veya yavaş indiriliyor'}
• Shopify API çok yavaş yanıt veriyor
• İnternet bağlantısı yavaş

💡 Çözüm Önerileri:
${fastMode ? 
  '• Daha küçük XML dosyası kullanın\n• XML\'i optimize edin\n• Tekrar deneyin' :
  '• Hızlı Modu aktifleştirin\n• Daha az ürünle test yapın (3-5 ürün)\n• İnternet bağlantınızı kontrol edin'
}
        `;
      } else if (error.message.includes('504') || error.message.includes('Gateway Timeout')) {
        errorMessage = 'Sunucu zaman aşımı (504 Gateway Timeout)';
        errorDetails = `
🚨 Sunucu Timeout Hatası:
• Serverless function 10 dakika limitini aştı
• XML dosyası çok büyük veya işleme çok uzun sürüyor

💡 Çözüm Önerileri:
• Daha az ürünle sync yapın (max 10-20)
• XML'i optimize edin
• Tekrar deneyin
        `;
      } else if (error.message.includes('JSON') || error.message.includes('parse')) {
        errorMessage = 'Sunucu yanıt formatı hatası';
        errorDetails = `
🚨 Response Parse Hatası:
• Sunucu geçersiz JSON yanıtı gönderdi
• API endpoint sorunu olabilir

💡 Çözüm Önerileri:
• Sayfayı yenileyin ve tekrar deneyin
• Birkaç dakika bekleyip tekrar deneyin
• Console'da detaylı hatayı kontrol edin
        `;
      }
      
      setSyncDetails({ 
        error: errorMessage,
        details: errorDetails
      });
      
      alert('❌ Senkronizasyon başarısız oldu: ' + errorMessage);
    }
  };

  useEffect(() => {
    testConnections();
  }, []);

  const getStatusBadge = (status) => {
    const statusMap = {
      pending: { class: 'status-pending', text: 'Bekleniyor' },
      testing: { class: 'status-pending', text: 'Test Ediliyor...' },
      connected: { class: 'status-connected', text: 'Bağlandı' },
      failed: { class: 'status-failed', text: 'Başarısız' }
    };
    
    const statusInfo = statusMap[status] || statusMap.pending;
    return <span className={`status-badge ${statusInfo.class}`}>{statusInfo.text}</span>;
  };

  return (
    <div className="container">
      <div className="nav">
        <h1 className="text-xl" style={{color: 'white', margin: 0}}>Shopify XML Sync Panel</h1>
        <div style={{marginLeft: 'auto', display: 'flex', gap: '12px'}}>
          <Link to="/settings">⚙️ Ayarlar</Link>
          <button onClick={handleLogout} className="btn" style={{padding: '4px 12px', fontSize: '12px'}}>
            Çıkış
          </button>
        </div>
      </div>

      <div className="grid grid-3">
        {/* Shopify API Status */}
        <div className="card">
          <h3 className="text-lg mb-4">🛍️ Shopify API</h3>
          <div className="mb-4">
            Durum: {getStatusBadge(connectionStatus.shopify.status)}
          </div>
          {connectionStatus.shopify.data && connectionStatus.shopify.data.storeName && (
            <div>
              <p><strong>Mağaza:</strong> {connectionStatus.shopify.data.storeName}</p>
              <p><strong>Ürün Sayısı:</strong> {connectionStatus.shopify.data.productCount || 0}</p>
              <p><strong>Son Güncelleme:</strong> {connectionStatus.shopify.data.lastUpdated ? new Date(connectionStatus.shopify.data.lastUpdated).toLocaleString('tr-TR') : 'Bilinmiyor'}</p>
              <p><strong>Bağlantı:</strong> <span style={{color: 'green'}}>✓ Sağlıklı</span></p>
            </div>
          )}
          {connectionStatus.shopify.status === 'failed' && (
            <p style={{color: 'red'}}>Shopify bağlantısı kurulamadı. Ayarlarda API bilgilerinizi kontrol edin.</p>
          )}
        </div>

        {/* XML Status */}
        <div className="card">
          <h3 className="text-lg mb-4">📄 XML Verisi</h3>
          <div className="mb-4">
            Durum: {getStatusBadge(connectionStatus.xml.status)}
          </div>
          {connectionStatus.xml.data && connectionStatus.xml.data.products !== undefined && (
            <div>
              <p><strong>📊 Ürün İstatistikleri:</strong></p>
              <div style={{marginLeft: '16px', marginBottom: '12px'}}>
                <p><strong>Toplam XML Ürün:</strong> {connectionStatus.xml.data.products || 0}</p>
                <p><strong>Benzersiz Ürün:</strong> {connectionStatus.xml.data.uniqueProducts || 0}</p>
                <p><strong>Benzersiz Stok Kodu:</strong> {connectionStatus.xml.data.uniqueStockCodes || 0}</p>
                <p><strong>Duplicate Ürün:</strong> {connectionStatus.xml.data.duplicateCount || 0}</p>
              </div>
              
              <p><strong>XML Yapısı:</strong> {connectionStatus.xml.data.structure || 'Bilinmiyor'}</p>
              <p><strong>XML Boyutu:</strong> {connectionStatus.xml.data.xmlInfo?.totalSize ? (connectionStatus.xml.data.xmlInfo.totalSize / 1024 / 1024).toFixed(2) + ' MB' : 'Bilinmiyor'}</p>
              <p><strong>Encoding:</strong> {connectionStatus.xml.data.xmlInfo?.encoding || 'Bilinmiyor'}</p>
              
              {connectionStatus.xml.data.analysis && (
                <div style={{marginTop: '8px', fontSize: '14px', background: '#f8f9fa', padding: '8px', borderRadius: '4px'}}>
                  <p><strong>📈 Analiz:</strong></p>
                  <p>Benzersiz Oran: {connectionStatus.xml.data.analysis.uniqueRatio}</p>
                  <p>Duplicate Oran: {connectionStatus.xml.data.analysis.duplicateRatio}</p>
                </div>
              )}
              
              {connectionStatus.xml.data.xmlInfo && (
                <div style={{marginTop: '8px', fontSize: '14px'}}>
                  <p><strong>Özellikler:</strong></p>
                  <ul style={{margin: '4px 0', paddingLeft: '20px'}}>
                    <li>Stok Kodları: {connectionStatus.xml.data.xmlInfo.hasStockCodes ? '✓' : '✗'}</li>
                    <li>CDATA Format: {connectionStatus.xml.data.xmlInfo.hasCDATA ? '✓' : '✗'}</li>
                    <li>Kategoriler: {connectionStatus.xml.data.xmlInfo.hasCategories ? '✓' : '✗'}</li>
                  </ul>
                </div>
              )}
              
              {connectionStatus.xml.data.sampleProducts && connectionStatus.xml.data.sampleProducts.length > 0 && (
                <details style={{marginTop: '8px', fontSize: '12px', color: '#666'}}>
                  <summary>🔍 Benzersiz Ürün Örnekleri (İlk 5)</summary>
                  {connectionStatus.xml.data.sampleProducts.map((product, index) => (
                    <div key={index} style={{marginTop: '8px', padding: '8px', background: '#f5f5f5', borderRadius: '4px'}}>
                      <p><strong>ID:</strong> {product.id}</p>
                      <p><strong>Stok Kodu:</strong> {product.stokKodu}</p>
                      <p><strong>Ürün Adı:</strong> {product.urunIsmi}</p>
                      <p><strong>Kategori:</strong> {product.kategori}</p>
                    </div>
                  ))}
                </details>
              )}
              
              {connectionStatus.xml.data.duplicateExamples && connectionStatus.xml.data.duplicateExamples.length > 0 && (
                <details style={{marginTop: '8px', fontSize: '12px', color: '#e74c3c'}}>
                  <summary>⚠️ Duplicate Ürün Örnekleri</summary>
                  {connectionStatus.xml.data.duplicateExamples.map((dup, index) => (
                    <div key={index} style={{marginTop: '8px', padding: '8px', background: '#fdf2f2', borderRadius: '4px', border: '1px solid #fecaca'}}>
                      <p><strong>ID:</strong> {dup.id}</p>
                      <p><strong>Stok Kodu:</strong> {dup.stokKodu}</p>
                      <p><strong>Pozisyon:</strong> {dup.position}. sırada</p>
                    </div>
                  ))}
                </details>
              )}
              
              <p><strong>Son Güncelleme:</strong> {new Date().toLocaleString('tr-TR')}</p>
              <p><strong>Akış:</strong> <span style={{color: 'green'}}>✓ Sağlıklı</span></p>
            </div>
          )}
          {connectionStatus.xml.status === 'failed' && (
            <div>
              <p style={{color: 'red'}}>
                ❌ XML verisi alınamadı. 
                {connectionStatus.xml.error && (
                  <span style={{display: 'block', marginTop: '8px', fontSize: '14px'}}>
                    <strong>Hata:</strong> {connectionStatus.xml.error}
                  </span>
                )}
              </p>
              
              <div style={{marginTop: '12px', padding: '12px', background: '#fef2f2', borderRadius: '8px', fontSize: '14px'}}>
                <p><strong>💡 Çözüm Önerileri:</strong></p>
                <ul style={{marginLeft: '20px', marginTop: '8px'}}>
                  <li>XML URL'inin doğru olduğunu kontrol edin</li>
                  <li>XML dosyası çok büyükse, sunucu zaman aşımına uğrayabilir</li>
                  <li>İnternet bağlantınızı kontrol edin</li>
                  <li>Birkaç dakika bekleyip tekrar deneyin</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Google Connection Status */}
        <div className="card">
          <h3 className="text-lg mb-4">📊 Google Sheets</h3>
          <div className="mb-4">
            Durum: {getStatusBadge(connectionStatus.google.status)}
          </div>
          {connectionStatus.google.data && connectionStatus.google.data.sheetName && (
            <div>
              <p><strong>Sayfa Adı:</strong> {connectionStatus.google.data.sheetName}</p>
              <p><strong>Sayfa Sayısı:</strong> {connectionStatus.google.data.sheetCount || 0}</p>
              <p><strong>Son Güncelleme:</strong> {connectionStatus.google.data.lastUpdated ? new Date(connectionStatus.google.data.lastUpdated).toLocaleString('tr-TR') : 'Bilinmiyor'}</p>
              <p><strong>Bağlantı:</strong> <span style={{color: 'green'}}>✓ Aktif</span></p>
            </div>
          )}
          {connectionStatus.google.status === 'failed' && (
            <p style={{color: 'red'}}>Google Sheets bağlantısı kurulamadı. API anahtarınızı kontrol edin.</p>
          )}
        </div>
      </div>

      {/* Synchronization Section */}
      <div className="card">
        <h2 className="text-xl mb-6">🔄 Senkronizasyon</h2>
        <p className="mb-4">
          XML'den ürün ID'leri çekilip Shopify API üzerinden envantere bakılacak. 
          Mevcut ürünler güncellenecek, yeni ürünler eklenecek.
        </p>
        
        <div className="mb-4">
          <strong>İşlenecek veriler:</strong>
          <ul style={{marginLeft: '20px', marginTop: '8px'}}>
            <li>Ürün bilgileri ve açıklamaları</li>
            <li>Varyantlar ve özellikler</li>
            <li>Stok miktarları</li>
            <li>Ürün görselleri</li>
            <li>Etiketler ve kategoriler</li>
          </ul>
        </div>

        <div className="mb-4">
          <div className="form-check">
            <input 
              className="form-check-input" 
              type="checkbox" 
              id="fastMode"
              checked={fastMode}
              onChange={(e) => setFastMode(e.target.checked)}
            />
            <label className="form-check-label" htmlFor="fastMode">
              ⚡ Hızlı Mod (Büyük XML dosyaları için - sadece ilk 3 ürün sync'i, 15 saniye timeout)
            </label>
          </div>
        </div>

        {syncStatus === 'idle' && (
          <button 
            onClick={startSync} 
            className="btn btn-success"
            disabled={connectionStatus.shopify.status !== 'connected' || connectionStatus.xml.status !== 'connected'}
          >
            🚀 Senkronizasyonu Başlat
          </button>
        )}
        
        {syncStatus === 'running' && (
          <div>
            <button className="btn" disabled>
              ⏳ Senkronizasyon Devam Ediyor...
            </button>
            <div style={{marginTop: '12px', padding: '12px', background: '#f3f4f6', borderRadius: '8px'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '8px'}}>
                <span>İlerleme:</span>
                <span>%60</span>
              </div>
              <div style={{width: '100%', height: '8px', background: '#e5e7eb', borderRadius: '4px'}}>
                <div style={{width: '60%', height: '100%', background: '#10b981', borderRadius: '4px', transition: 'width 0.3s'}}></div>
              </div>
            </div>
          </div>
        )}
        
        {syncStatus === 'completed' && syncDetails && (
          <div>
            <button onClick={() => setSyncStatus('idle')} className="btn btn-success">
              ✅ Senkronizasyon Tamamlandı - Yeniden Başlat
            </button>
            
            <div style={{marginTop: '12px', padding: '12px', background: '#f0f9f4', border: '1px solid #bbf7d0', borderRadius: '8px'}}>
              <h4 style={{margin: '0 0 8px 0', color: '#059669'}}>📊 Senkronizasyon Sonuçları</h4>
              
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', marginBottom: '12px'}}>
                <div style={{background: 'white', padding: '8px', borderRadius: '4px', textAlign: 'center'}}>
                  <div style={{fontSize: '20px', fontWeight: 'bold', color: '#059669'}}>{syncDetails.productsCreated}</div>
                  <div style={{fontSize: '12px', color: '#666'}}>Yeni Ürün</div>
                </div>
                <div style={{background: 'white', padding: '8px', borderRadius: '4px', textAlign: 'center'}}>
                  <div style={{fontSize: '20px', fontWeight: 'bold', color: '#0369a1'}}>{syncDetails.productsUpdated}</div>
                  <div style={{fontSize: '12px', color: '#666'}}>Güncellenen</div>
                </div>
                <div style={{background: 'white', padding: '8px', borderRadius: '4px', textAlign: 'center'}}>
                  <div style={{fontSize: '20px', fontWeight: 'bold', color: '#9333ea'}}>{syncDetails.productsSkipped}</div>
                  <div style={{fontSize: '12px', color: '#666'}}>Atlanan</div>
                </div>
                <div style={{background: 'white', padding: '8px', borderRadius: '4px', textAlign: 'center'}}>
                  <div style={{fontSize: '20px', fontWeight: 'bold', color: '#dc2626'}}>{syncDetails.errors?.length || 0}</div>
                  <div style={{fontSize: '12px', color: '#666'}}>Hata</div>
                </div>
              </div>
              
              <div style={{fontSize: '14px', marginBottom: '8px'}}>
                <strong>⏱️ Süre:</strong> {syncDetails.duration} | 
                <strong> 📅 Tarih:</strong> {new Date(syncDetails.timestamp).toLocaleString('tr-TR')}
              </div>
              
              {syncDetails.details && syncDetails.details.length > 0 && (
                <details style={{fontSize: '12px', marginTop: '8px'}}>
                  <summary style={{cursor: 'pointer', fontWeight: 'bold'}}>🔍 İşlem Detayları ({syncDetails.details.length})</summary>
                  <div style={{maxHeight: '150px', overflowY: 'auto', marginTop: '8px', background: 'white', padding: '8px', borderRadius: '4px'}}>
                    {syncDetails.details.map((detail, index) => (
                      <div key={index} style={{marginBottom: '4px', padding: '4px', borderBottom: '1px solid #f3f4f6'}}>
                        <span style={{
                          display: 'inline-block',
                          padding: '2px 6px',
                          borderRadius: '3px',
                          fontSize: '10px',
                          marginRight: '8px',
                          background: detail.action === 'created' ? '#dcfce7' : 
                                   detail.action === 'updated' ? '#dbeafe' : '#fef3c7',
                          color: detail.action === 'created' ? '#166534' : 
                                detail.action === 'updated' ? '#1e40af' : '#92400e'
                        }}>
                          {detail.action.toUpperCase()}
                        </span>
                        <span style={{fontWeight: 'bold'}}>ID {detail.xmlId}:</span> {detail.title.substring(0, 40)}...
                        {detail.changes && (
                          <div style={{marginLeft: '60px', color: '#666', fontSize: '10px'}}>
                            {detail.changes.join(', ')}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
              
              {syncDetails.errors && syncDetails.errors.length > 0 && (
                <details style={{fontSize: '12px', marginTop: '8px'}}>
                  <summary style={{cursor: 'pointer', fontWeight: 'bold', color: '#dc2626'}}>❌ Hatalar ({syncDetails.errors.length})</summary>
                  <div style={{maxHeight: '100px', overflowY: 'auto', marginTop: '8px', background: '#fef2f2', padding: '8px', borderRadius: '4px'}}>
                    {syncDetails.errors.map((error, index) => (
                      <div key={index} style={{marginBottom: '4px', color: '#dc2626', fontSize: '11px'}}>
                        {error}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        )}
        
        {syncStatus === 'failed' && (
          <div>
            <button onClick={() => setSyncStatus('idle')} className="btn btn-danger">
              ❌ Senkronizasyon Başarısız - Tekrar Dene
            </button>
            {syncDetails && syncDetails.error && (
              <div style={{marginTop: '8px', padding: '8px', background: '#fef2f2', borderRadius: '4px', color: '#dc2626', fontSize: '14px'}}>
                <strong>Hata:</strong> {syncDetails.error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
