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
    // Shopify API Test
    setConnectionStatus(prev => ({
      ...prev,
      shopify: { status: 'testing', data: {} }
    }));
    
    // Simulated API call
    setTimeout(() => {
      setConnectionStatus(prev => ({
        ...prev,
        shopify: {
          status: 'connected',
          data: {
            storeName: 'My Store',
            productCount: 156,
            variantCount: 324,
            stockCount: 1234
          }
        }
      }));
    }, 2000);

    // XML Test
    setConnectionStatus(prev => ({
      ...prev,
      xml: { status: 'testing', data: {} }
    }));
    
    setTimeout(() => {
      setConnectionStatus(prev => ({
        ...prev,
        xml: {
          status: 'connected',
          data: {
            version: '2.1',
            format: 'Sentos XML',
            productCount: 142,
            variantCount: 298,
            stockCount: 1156
          }
        }
      }));
    }, 3000);

    // Google Test
    setConnectionStatus(prev => ({
      ...prev,
      google: { status: 'testing', data: {} }
    }));
    
    setTimeout(() => {
      setConnectionStatus(prev => ({
        ...prev,
        google: {
          status: 'connected',
          data: {
            sheetsConnected: true,
            sheetName: 'Product Data'
          }
        }
      }));
    }, 4000);
  };

  const startSync = async () => {
    setSyncStatus('running');
    
    // Simulate sync process
    setTimeout(() => {
      setSyncStatus('completed');
      alert('Senkronizasyon tamamlandı! 142 ürün güncellendi, 14 yeni ürün eklendi.');
    }, 5000);
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
          {connectionStatus.shopify.data.storeName && (
            <div>
              <p><strong>Mağaza Adı:</strong> {connectionStatus.shopify.data.storeName}</p>
              <p><strong>Ürün Sayısı:</strong> {connectionStatus.shopify.data.productCount}</p>
              <p><strong>Varyant Sayısı:</strong> {connectionStatus.shopify.data.variantCount}</p>
              <p><strong>Stok Adedi:</strong> {connectionStatus.shopify.data.stockCount}</p>
            </div>
          )}
        </div>

        {/* Sentos XML Status */}
        <div className="card">
          <h3 className="text-lg mb-4">📄 Sentos XML</h3>
          <div className="mb-4">
            Durum: {getStatusBadge(connectionStatus.xml.status)}
          </div>
          {connectionStatus.xml.data.version && (
            <div>
              <p><strong>XML Sürümü:</strong> {connectionStatus.xml.data.version}</p>
              <p><strong>XML Format:</strong> {connectionStatus.xml.data.format}</p>
              <p><strong>Ürün Sayısı:</strong> {connectionStatus.xml.data.productCount}</p>
              <p><strong>Varyant Sayısı:</strong> {connectionStatus.xml.data.variantCount}</p>
              <p><strong>Stok Adedi:</strong> {connectionStatus.xml.data.stockCount}</p>
            </div>
          )}
        </div>

        {/* Google Connection Status */}
        <div className="card">
          <h3 className="text-lg mb-4">📊 Google Bağlantısı</h3>
          <div className="mb-4">
            Durum: {getStatusBadge(connectionStatus.google.status)}
          </div>
          {connectionStatus.google.data.sheetsConnected && (
            <div>
              <p><strong>Google Sheets:</strong> Bağlı</p>
              <p><strong>Sayfa Adı:</strong> {connectionStatus.google.data.sheetName}</p>
            </div>
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
        
        {syncStatus === 'completed' && (
          <div>
            <button onClick={() => setSyncStatus('idle')} className="btn btn-success">
              ✅ Senkronizasyon Tamamlandı - Yeniden Başlat
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
