with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

contact_info_view = '''

class WhatsAppContactInfoView(APIView):
    """
    Proxies contact info fetching from WAHA.
    GET /api/whatsapp/contact-info/<chat_id>/
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, chat_id):
        import urllib.request
        import urllib.error
        import os
        import json as _json

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session = "mohan"

        url = f"{waha_url}/api/{session}/contacts/{chat_id}"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                return Response(data)
        except Exception as e:
            return Response({"detail": str(e)}, status=404)
'''

content = content.rstrip() + contact_info_view

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

with open('whatsapp/urls.py', 'r', encoding='utf-8') as f:
    urls_content = f.read()

old_import = '    WhatsAppProfilePicView,'
new_import = '''    WhatsAppProfilePicView,
    WhatsAppContactInfoView,'''
urls_content = urls_content.replace(old_import, new_import)

old_path = '    path("profile-pic/<str:chat_id>/", WhatsAppProfilePicView.as_view(), name="whatsapp-profile-pic"),'
new_path = '''    path("profile-pic/<str:chat_id>/", WhatsAppProfilePicView.as_view(), name="whatsapp-profile-pic"),
    path("contact-info/<str:chat_id>/", WhatsAppContactInfoView.as_view(), name="whatsapp-contact-info"),'''
urls_content = urls_content.replace(old_path, new_path)

with open('whatsapp/urls.py', 'w', encoding='utf-8') as f:
    f.write(urls_content)
print('Added contact info proxy endpoint')
