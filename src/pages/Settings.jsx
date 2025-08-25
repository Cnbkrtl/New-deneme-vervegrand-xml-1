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
    if (type === 'shopify') endpoint = '/api/shopify';
    if (type === 'xml') endpoint = '/api/xml';
    if (type === 'google') endpoint = '/api/google';
    try {
      const response = await fetch(endpoint);
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
      {/* ...existing code... */}
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
      {/* ...existing code... */}
    </div>
  );
};

export default Settings;
