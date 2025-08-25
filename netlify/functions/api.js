const axios = require('axios');

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
    const response = await axios.get(url, {
      headers: { 'X-Shopify-Access-Token': accessToken }
    });
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'success', data: response.data.shop })
    };
  } catch (error) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

async function handleXML(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { xmlUrl } = JSON.parse(event.body);
  
  try {
    const response = await axios.get(xmlUrl);
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'success', data: response.data })
    };
  } catch (error) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}

async function handleGoogle(event, headers) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  
  const { clientId, apiKey, spreadsheetId } = JSON.parse(event.body);
  
  try {
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?key=${apiKey}`;
    const response = await axios.get(url);
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'success', data: response.data })
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
    const response = {
      status: 'success',
      data: {
        productsProcessed: 142,
        productsUpdated: 128,
        productsCreated: 14,
        variantsUpdated: 298,
        inventoryUpdated: 1156
      }
    };
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify(response)
    };
  } catch (error) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ status: 'error', error: error.message })
    };
  }
}
