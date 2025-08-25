const axios = require('axios');

exports.handler = async (event, context) => {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  };

  // Handle preflight requests
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers,
      body: '',
    };
  }

  try {
    const { path } = event;
    const method = event.httpMethod;
    
    // API routing
    if (path.includes('/shopify')) {
      return await handleShopify(event, method);
    } else if (path.includes('/xml')) {
      return await handleXML(event, method);
    } else if (path.includes('/google')) {
      return await handleGoogle(event, method);
    } else if (path.includes('/sync')) {
      return await handleSync(event, method);
    }

    return {
      statusCode: 404,
      headers,
      body: JSON.stringify({ error: 'Endpoint not found' }),
    };
  } catch (error) {
    console.error('API Error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: 'Internal server error' }),
    };
  }
};

async function handleShopify(event, method) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
  };

  if (method === 'POST') {
    const { apiKey, apiSecret, storeUrl, accessToken } = JSON.parse(event.body);
    try {
      // Shopify mağaza bilgisi çekme
      const shopUrl = `https://${storeUrl}/admin/api/2023-01/shop.json`;
      const response = await axios.get(shopUrl, {
        headers: {
          'X-Shopify-Access-Token': accessToken,
          'Content-Type': 'application/json',
        },
      });
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ status: 'connected', data: response.data.shop }),
      };
    } catch (error) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ status: 'failed', error: error.message }),
      };
    }
  }
  return {
    statusCode: 405,
    headers,
    body: JSON.stringify({ error: 'Method not allowed' }),
  };
}

async function handleXML(event, method) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
  };
  if (method === 'POST') {
    const { xmlUrl } = JSON.parse(event.body);
    try {
      const response = await axios.get(xmlUrl);
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ status: 'connected', data: response.data }),
      };
    } catch (error) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ status: 'failed', error: error.message }),
      };
    }
  }
  return {
    statusCode: 405,
    headers,
    body: JSON.stringify({ error: 'Method not allowed' }),
  };
}

async function handleGoogle(event, method) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
  };
  if (method === 'POST') {
    const { clientId, apiKey, spreadsheetId } = JSON.parse(event.body);
    try {
      // Google Sheets API test (public sheet için)
      const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?key=${apiKey}`;
      const response = await axios.get(url);
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ status: 'connected', data: response.data }),
      };
    } catch (error) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ status: 'failed', error: error.message }),
      };
    }
  }
  return {
    statusCode: 405,
    headers,
    body: JSON.stringify({ error: 'Method not allowed' }),
  };
}

async function handleSync(event, method) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
  };

  if (method === 'POST') {
    try {
      // In a real implementation, this would:
      // 1. Fetch XML data
      // 2. Parse products and variants
      // 3. Check existing products in Shopify
      // 4. Update existing products or create new ones
      // 5. Update inventory levels
      // 6. Handle images and tags
      
      // Simulate sync process
      const response = {
        status: 'success',
        data: {
          productsProcessed: 142,
          productsUpdated: 128,
          productsCreated: 14,
          variantsUpdated: 298,
          inventoryUpdated: 1156,
          errors: []
        }
      };

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify(response),
      };
    } catch (error) {
      return {
        statusCode: 500,
        headers,
        body: JSON.stringify({ status: 'failed', error: error.message }),
      };
    }
  }

  return {
    statusCode: 405,
    headers,
    body: JSON.stringify({ error: 'Method not allowed' }),
  };
}
