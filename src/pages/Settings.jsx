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

  // Test durumları
  const [testStatus, setTestStatus] = useState({
    shopify: 'idle', // idle | loading | success | error
    xml: 'idle',
    google: 'idle'
  });

  // Test fonksiyonu
  const handleTest = async (type) => {
    setTestStatus(prev => ({ ...prev, [type]: 'loading' }));
    let endpoint = '';
    let body = {};

    if (type === 'shopify') {
      endpoint = '/api/shopify';
      body = shopifySettings;
    }
    if (type === 'xml') {
      endpoint = '/api/xml';
      body = xmlSettings;
    }
    if (type === 'google') {
      endpoint = '/api/google';
      body = googleSettings;
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error('Network response was not ok');
      setTestStatus(prev => ({ ...prev, [type]: 'success' }));
    } catch (err) {
      setTestStatus(prev => ({ ...prev, [type]: 'error' }));
    }
    setTimeout(() => setTestStatus(prev => ({ ...prev, [type]: 'idle' })), 2500);
  };

  // İkon render
  const renderTestIcon = (status) => {
    if (status === 'loading') return <span className="spinner" style={{marginLeft: 8}}></span>;
    if (status === 'success') return <span style={{color: 'green', marginLeft: 8}}>✓</span>;
    if (status === 'error') return <span style={{color: 'red', marginLeft: 8}}>✗</span>;
    return null;
  };

  return (
    <div className="container">
      <h1 className="main-title">Ayarlar</h1>
      {saveStatus && <div className="save-status">{saveStatus}</div>}

      {/* Shopify Settings */}
      <div className="card">
        <h2 className="text-lg mb-4">🛍️ Shopify Ayarları</h2>
        <form onSubmit={handleShopifySubmit} className="space-y-4">
          <div>
            <label htmlFor="shopifyApiKey">API Key</label>
            <input
              id="shopifyApiKey"
              type="text"
              value={shopifySettings.apiKey}
              onChange={(e) => setShopifySettings({ ...shopifySettings, apiKey: e.target.value })}
              className="input"
              placeholder="Shopify API Anahtarınız"
            />
          </div>
          <div>
            <label htmlFor="shopifyApiSecret">API Secret</label>
            <input
              id="shopifyApiSecret"
              type="password"
              value={shopifySettings.apiSecret}
              onChange={(e) => setShopifySettings({ ...shopifySettings, apiSecret: e.target.value })}
              className="input"
              placeholder="Shopify API Secret"
            />
          </div>
          <div>
            <label htmlFor="shopifyStoreUrl">Mağaza URL</label>
            <input
              id="shopifyStoreUrl"
              type="text"
              value={shopifySettings.storeUrl}
              onChange={(e) => setShopifySettings({ ...shopifySettings, storeUrl: e.target.value })}
              className="input"
              placeholder="ornek.myshopify.com"
            />
          </div>
          <div>
            <label htmlFor="shopifyAccessToken">Access Token</label>
            <input
              id="shopifyAccessToken"
              type="password"
              value={shopifySettings.accessToken}
              onChange={(e) => setShopifySettings({ ...shopifySettings, accessToken: e.target.value })}
              className="input"
              placeholder="Shopify Erişim Token"
            />
          </div>
          <button type="submit" className="btn">
            Shopify Ayarlarını Kaydet
          </button>
        </form>
      </div>

      {/* XML Settings */}
      <div className="card">
        <h2 className="text-lg mb-4">📄 XML Ayarları</h2>
        <form onSubmit={handleXmlSubmit} className="space-y-4">
          <div>
            <label htmlFor="xmlUrl">XML URL</label>
            <input
              id="xmlUrl"
              type="text"
              value={xmlSettings.xmlUrl}
              onChange={(e) => setXmlSettings({ xmlUrl: e.target.value })}
              className="input"
              placeholder="XML Dosya Adresi"
            />
          </div>
          <button type="submit" className="btn">
            XML Ayarlarını Kaydet
          </button>
        </form>
      </div>

      {/* Google API Settings */}
      <div className="card">
        <h2 className="text-lg mb-4">📊 Google API Ayarları</h2>
        <form onSubmit={handleGoogleSubmit} className="space-y-4">
          <div>
            <label htmlFor="googleClientId">Client ID</label>
            <input
              id="googleClientId"
              type="text"
              value={googleSettings.clientId}
              onChange={(e) => setGoogleSettings({ ...googleSettings, clientId: e.target.value })}
              className="input"
              placeholder="Google Client ID"
            />
          </div>
          <div>
            <label htmlFor="googleApiKey">API Key</label>
            <input
              id="googleApiKey"
              type="text"
              value={googleSettings.apiKey}
              onChange={(e) => setGoogleSettings({ ...googleSettings, apiKey: e.target.value })}
              className="input"
              placeholder="Google API Key"
            />
          </div>
          <div>
            <label htmlFor="googleSpreadsheetId">Spreadsheet ID</label>
            <input
              id="googleSpreadsheetId"
              type="text"
              value={googleSettings.spreadsheetId}
              onChange={(e) => setGoogleSettings({ ...googleSettings, spreadsheetId: e.target.value })}
              className="input"
              placeholder="Google Spreadsheet ID"
            />
          </div>
          <button type="submit" className="btn">
            Google Ayarlarını Kaydet
          </button>
        </form>
      </div>

      {/* Test Connections */}
      <div className="card">
        <h2 className="text-lg mb-6">🔧 Bağlantı Testleri</h2>
        <div className="grid grid-3">
          <button className="btn" onClick={() => handleTest('shopify')} disabled={testStatus.shopify === 'loading'}>
            🛍️ Shopify Test Et {renderTestIcon(testStatus.shopify)}
          </button>
          <button className="btn" onClick={() => handleTest('xml')} disabled={testStatus.xml === 'loading'}>
            📄 XML Test Et {renderTestIcon(testStatus.xml)}
          </button>
          <button className="btn" onClick={() => handleTest('google')} disabled={testStatus.google === 'loading'}>
            📊 Google Test Et {renderTestIcon(testStatus.google)}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
