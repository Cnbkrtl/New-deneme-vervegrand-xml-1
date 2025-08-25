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
    // Test Shopify connection
    const { apiKey, apiSecret, storeUrl, accessToken } = JSON.parse(event.body);
    
    try {
      // In a real implementation, you would make actual API calls to Shopify
      // For now, we'll simulate a successful connection
      const response = {
        status: 'connected',
        data: {
          storeName: 'Demo Store',
          productCount: 156,
          variantCount: 324,
          stockCount: 1234
        }
      };

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify(response),
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
    // Test XML connection and parse
    const { xmlUrl } = JSON.parse(event.body);
    
    try {
      // In a real implementation, you would fetch and parse the XML
      // For now, we'll simulate a successful XML parse
      const response = {
        status: 'connected',
        data: {
          version: '2.1',
          format: 'Sentos XML',
          productCount: 142,
          variantCount: 298,
          stockCount: 1156
        }
      };

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify(response),
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
    // Test Google Sheets connection
    const { clientId, apiKey, spreadsheetId } = JSON.parse(event.body);
    
    try {
      // In a real implementation, you would authenticate with Google API
      // For now, we'll simulate a successful connection
      const response = {
        status: 'connected',
        data: {
          sheetsConnected: true,
          sheetName: 'Product Data'
        }
      };

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify(response),
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
