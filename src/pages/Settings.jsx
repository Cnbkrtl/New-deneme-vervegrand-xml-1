import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const Settings = () => {
  const [shopifySettings, setShopifySettings] = useState({
    apiKey: localStorage.getItem('shopify_api_key') || '',
    apiSecret: localStorage.getItem('shopify_api_secret') || '',
    storeUrl: localStorage.getItem('shopify_store_url') || '',
    accessToken: localStorage.getItem('shopify_access_token') || ''
  });

  const [xmlSettings, setXmlSettings] = useState({
    xmlUrl: localStorage.getItem('xml_url') || ''
  });

  const [googleSettings, setGoogleSettings] = useState({
    clientId: localStorage.getItem('google_client_id') || '',
    apiKey: localStorage.getItem('google_api_key') || '',
    spreadsheetId: localStorage.getItem('google_spreadsheet_id') || ''
  });

  const [saveStatus, setSaveStatus] = useState('');

  const handleShopifySubmit = (e) => {
    e.preventDefault();
    // Save to localStorage (in production, this would be sent to a secure backend)
    localStorage.setItem('shopify_api_key', shopifySettings.apiKey);
    localStorage.setItem('shopify_api_secret', shopifySettings.apiSecret);
    localStorage.setItem('shopify_store_url', shopifySettings.storeUrl);
    localStorage.setItem('shopify_access_token', shopifySettings.accessToken);
    
    setSaveStatus('Shopify ayarları kaydedildi!');
    setTimeout(() => setSaveStatus(''), 3000);
  };

  const handleXmlSubmit = (e) => {
    e.preventDefault();
    localStorage.setItem('xml_url', xmlSettings.xmlUrl);
    
    setSaveStatus('XML ayarları kaydedildi!');
    setTimeout(() => setSaveStatus(''), 3000);
  };

  const handleGoogleSubmit = (e) => {
    e.preventDefault();
    localStorage.setItem('google_client_id', googleSettings.clientId);
    localStorage.setItem('google_api_key', googleSettings.apiKey);
    localStorage.setItem('google_spreadsheet_id', googleSettings.spreadsheetId);
    
    setSaveStatus('Google API ayarları kaydedildi!');
    setTimeout(() => setSaveStatus(''), 3000);
  };

  return (
    <div className="container">
      <div className="nav">
        <h1 className="text-xl" style={{color: 'white', margin: 0}}>⚙️ Ayarlar</h1>
        <div style={{marginLeft: 'auto'}}>
          <Link to="/">🏠 Ana Panel</Link>
        </div>
      </div>

      {saveStatus && (
        <div className="card" style={{background: '#d1fae5', border: '1px solid #10b981'}}>
          <p style={{color: '#065f46', margin: 0}}>✅ {saveStatus}</p>
        </div>
      )}

      {/* Shopify API Settings */}
      <div className="card">
        <h2 className="text-lg mb-6">🛍️ Shopify API Ayarları</h2>
        <form onSubmit={handleShopifySubmit}>
          <div className="grid grid-2">
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>API Key</label>
              <input
                type="text"
                value={shopifySettings.apiKey}
                onChange={(e) => setShopifySettings({...shopifySettings, apiKey: e.target.value})}
                placeholder="Shopify API Key"
                className="input"
              />
            </div>
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>API Secret</label>
              <input
                type="password"
                value={shopifySettings.apiSecret}
                onChange={(e) => setShopifySettings({...shopifySettings, apiSecret: e.target.value})}
                placeholder="Shopify API Secret"
                className="input"
              />
            </div>
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>Store URL</label>
              <input
                type="text"
                value={shopifySettings.storeUrl}
                onChange={(e) => setShopifySettings({...shopifySettings, storeUrl: e.target.value})}
                placeholder="your-store.myshopify.com"
                className="input"
              />
            </div>
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>Access Token</label>
              <input
                type="password"
                value={shopifySettings.accessToken}
                onChange={(e) => setShopifySettings({...shopifySettings, accessToken: e.target.value})}
                placeholder="Shopify Access Token"
                className="input"
              />
            </div>
          </div>
          <button type="submit" className="btn">
            💾 Shopify Ayarlarını Kaydet
          </button>
        </form>
        
        <div style={{marginTop: '20px', padding: '12px', background: '#f3f4f6', borderRadius: '8px', fontSize: '14px'}}>
          <strong>ℹ️ Bilgi:</strong> Shopify Admin panelinden Private App oluşturarak API bilgilerinizi alabilirsiniz.
        </div>
      </div>

      {/* XML Connection Settings */}
      <div className="card">
        <h2 className="text-lg mb-6">📄 XML Bağlantı Ayarları</h2>
        <form onSubmit={handleXmlSubmit}>
          <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>XML URL</label>
          <input
            type="url"
            value={xmlSettings.xmlUrl}
            onChange={(e) => setXmlSettings({...xmlSettings, xmlUrl: e.target.value})}
            placeholder="https://example.com/products.xml"
            className="input"
          />
          <button type="submit" className="btn">
            💾 XML Ayarlarını Kaydet
          </button>
        </form>
        
        <div style={{marginTop: '20px', padding: '12px', background: '#f3f4f6', borderRadius: '8px', fontSize: '14px'}}>
          <strong>ℹ️ Bilgi:</strong> Sentos XML formatında ürün verilerinizin bulunduğu URL'yi girin.
        </div>
      </div>

      {/* Google API Settings */}
      <div className="card">
        <h2 className="text-lg mb-6">📊 Google API Ayarları</h2>
        <form onSubmit={handleGoogleSubmit}>
          <div className="grid grid-2">
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>Client ID</label>
              <input
                type="text"
                value={googleSettings.clientId}
                onChange={(e) => setGoogleSettings({...googleSettings, clientId: e.target.value})}
                placeholder="Google Client ID"
                className="input"
              />
            </div>
            <div>
              <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>API Key</label>
              <input
                type="password"
                value={googleSettings.apiKey}
                onChange={(e) => setGoogleSettings({...googleSettings, apiKey: e.target.value})}
                placeholder="Google API Key"
                className="input"
              />
            </div>
          </div>
          <label style={{display: 'block', marginBottom: '4px', fontWeight: '500'}}>Spreadsheet ID</label>
          <input
            type="text"
            value={googleSettings.spreadsheetId}
            onChange={(e) => setGoogleSettings({...googleSettings, spreadsheetId: e.target.value})}
            placeholder="Google Sheets Spreadsheet ID"
            className="input"
          />
          <button type="submit" className="btn">
            💾 Google Ayarlarını Kaydet
          </button>
        </form>
        
        <div style={{marginTop: '20px', padding: '12px', background: '#f3f4f6', borderRadius: '8px', fontSize: '14px'}}>
          <strong>ℹ️ Bilgi:</strong> Google Cloud Console'dan API credentials oluşturarak bilgilerinizi alabilirsiniz.
        </div>
      </div>

      {/* Test Connections */}
      <div className="card">
        <h2 className="text-lg mb-6">🔧 Bağlantı Testleri</h2>
        <div className="grid grid-3">
          <button 
            className="btn" 
            onClick={() => alert('Shopify bağlantısı test ediliyor...')}
          >
            🛍️ Shopify Test Et
          </button>
          <button 
            className="btn" 
            onClick={() => alert('XML bağlantısı test ediliyor...')}
          >
            📄 XML Test Et
          </button>
          <button 
            className="btn" 
            onClick={() => alert('Google bağlantısı test ediliyor...')}
          >
            📊 Google Test Et
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
