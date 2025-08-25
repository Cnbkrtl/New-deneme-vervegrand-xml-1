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

        const response = await fetch(`/api/${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        setConnectionStatus(prev => ({ ...prev, [key]: { status: 'connected', data: data.data || {} } }));
      } catch (error) {
        console.error(`Error testing ${key}:`, error);
        setConnectionStatus(prev => ({ ...prev, [key]: { status: 'failed', data: {} } }));
      }
    };

    await Promise.all([
      testEndpoint('shopify', 'shopify'),
      testEndpoint('xml', 'xml'),
      testEndpoint('google', 'google')
    ]);
  };

  const startSync = async () => {
    setSyncStatus('running');
    
    try {
      const response = await fetch('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      
      if (!response.ok) throw new Error('Sync failed');
      const data = await response.json();
      
      setSyncStatus('completed');
      alert(`Senkronizasyon tamamlandı! ${data.data.productsUpdated} ürün güncellendi, ${data.data.productsCreated} yeni ürün eklendi.`);
    } catch (error) {
      setSyncStatus('failed');
      alert('Senkronizasyon başarısız oldu: ' + error.message);
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
          {connectionStatus.xml.data && connectionStatus.xml.data.productCount !== undefined && (
            <div>
              <p><strong>Ürün Sayısı:</strong> {connectionStatus.xml.data.productCount || 0}</p>
              <p><strong>Benzersiz ID:</strong> {connectionStatus.xml.data.uniqueIds || 0}</p>
              <p><strong>Varyant Sayısı:</strong> {connectionStatus.xml.data.variantCount || 0}</p>
              <p><strong>XML Yapısı:</strong> {connectionStatus.xml.data.structure || 'Bilinmiyor'}</p>
              <p><strong>XML Boyutu:</strong> {connectionStatus.xml.data.xmlSize ? (connectionStatus.xml.data.xmlSize / 1024).toFixed(2) + ' KB' : 'Bilinmiyor'}</p>
              {connectionStatus.xml.data.debug && (
                <details style={{marginTop: '8px', fontSize: '12px', color: '#666'}}>
                  <summary>Debug Bilgileri</summary>
                  <p>Urun Tags: {connectionStatus.xml.data.debug.urunTags}</p>
                  <p>Product Tags: {connectionStatus.xml.data.debug.productTags}</p>
                  <p>Item Tags: {connectionStatus.xml.data.debug.itemTags}</p>
                </details>
              )}
              <p><strong>Son Güncelleme:</strong> {connectionStatus.xml.data.lastUpdated ? new Date(connectionStatus.xml.data.lastUpdated).toLocaleString('tr-TR') : 'Bilinmiyor'}</p>
              <p><strong>Akış:</strong> <span style={{color: connectionStatus.xml.data.healthy ? 'green' : 'red'}}>
                {connectionStatus.xml.data.healthy ? '✓ Sağlıklı' : '✗ Sorunlu'}
              </span></p>
            </div>
          )}
          {connectionStatus.xml.status === 'failed' && (
            <p style={{color: 'red'}}>XML verisi alınamadı. Ayarlarda XML URL'ini kontrol edin.</p>
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
        
        {syncStatus === 'failed' && (
          <div>
            <button onClick={() => setSyncStatus('idle')} className="btn btn-danger">
              ❌ Senkronizasyon Başarısız - Tekrar Dene
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
