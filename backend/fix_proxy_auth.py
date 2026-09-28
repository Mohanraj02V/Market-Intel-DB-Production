with open('whatsapp/views.py', 'r') as f:
    content = f.read()

# Remove IsAuthenticated from the proxy view - img tags can't send JWT headers
# The security is provided by the URL validation (only WAHA local URLs allowed)
old = '''class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA with API key authentication.
    The browser cannot directly access WAHA files (requires API key),
    so we proxy them through Django.
    
    GET /api/whatsapp/media-proxy/?url=http://localhost:3000/api/files/...
    """
    permission_classes = [IsAuthenticated]'''

new = '''class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA with API key authentication.
    The browser cannot directly access WAHA files (requires API key),
    so we proxy them through Django.

    No JWT auth required - img/video/audio tags cannot send auth headers.
    Security is enforced by validating the URL only points to the WAHA server.

    GET /api/whatsapp/media-proxy/?url=http://localhost:3000/api/files/...
    """
    authentication_classes = []
    permission_classes = []'''

content = content.replace(old, new)
with open('whatsapp/views.py', 'w') as f:
    f.write(content)
print('Done!')
