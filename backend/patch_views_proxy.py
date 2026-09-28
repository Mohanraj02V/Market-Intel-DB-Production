with open('whatsapp/views.py', 'r') as f:
    content = f.read()

# Add the proxy view at the end
proxy_view = '''

class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA with API key authentication.
    The browser cannot directly access WAHA files (requires API key),
    so we proxy them through Django.
    
    GET /api/whatsapp/media-proxy/?url=http://localhost:3000/api/files/...
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import urllib.request
        import urllib.error

        media_url = request.query_params.get("url", "")
        if not media_url:
            return Response({"detail": "Missing url parameter."}, status=400)

        # Security: only allow WAHA local file URLs
        waha_base = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        if not media_url.startswith(waha_base):
            return Response({"detail": "Forbidden URL."}, status=403)

        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        req = urllib.request.Request(media_url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
        except urllib.error.HTTPError as e:
            return Response({"detail": f"WAHA returned {e.code}"}, status=502)
        except Exception as e:
            return Response({"detail": str(e)}, status=502)

        from django.http import HttpResponse
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response
'''

# Add import for os at the top if not present
if 'import os' not in content:
    content = content.replace('import logging', 'import logging\nimport os')

content = content.rstrip() + proxy_view

with open('whatsapp/views.py', 'w') as f:
    f.write(content)
print('Done!')
