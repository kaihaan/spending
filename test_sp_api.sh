#!/bin/bash
# Test SP-API Integration

echo "🔍 Testing SP-API Authorization Endpoint..."
echo ""

# Test authorize endpoint
AUTH_RESPONSE=$(curl -s http://localhost:5000/api/amazon-business/authorize)
echo "Response:"
echo "$AUTH_RESPONSE" | python3 -m json.tool

# Extract authorization URL
AUTH_URL=$(echo "$AUTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('authorization_url', 'ERROR'))" 2>/dev/null)

if [[ "$AUTH_URL" == *"sellercentral.amazon.com"* ]]; then
    echo ""
    echo "✅ SUCCESS! SP-API authorization endpoint is working"
    echo ""
    echo "📋 Authorization URL:"
    echo "$AUTH_URL"
    echo ""
    echo "🔗 To test OAuth flow:"
    echo "   1. Open the frontend: http://localhost:5173/settings#data-sources"
    echo "   2. Click 'Connect' for Amazon Business"
    echo "   3. You'll be redirected to Amazon Seller Central"
    echo "   4. Authorize the app"
else
    echo ""
    echo "❌ ERROR: Authorization endpoint not working properly"
    echo "Response: $AUTH_RESPONSE"
fi
