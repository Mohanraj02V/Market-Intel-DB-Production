with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

profile_pic_view = '''

class WhatsAppProfilePicView(APIView):
    """
    Proxies profile picture fetching from WAHA.
    GET /api/whatsapp/profile-pic/<chat_id>/
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

        # Construct the URL to get the profile pic
        url = f"{waha_url}/api/{session}/contacts/{chat_id}/profile-picture"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                pic_url = data.get("profilePictureURL")
                if pic_url:
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(pic_url)
                else:
                    return Response({"detail": "No profile picture"}, status=404)
        except Exception as e:
            return Response({"detail": str(e)}, status=404)
'''

content = content.rstrip() + profile_pic_view

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Added profile pic view')

with open('whatsapp/urls.py', 'r', encoding='utf-8') as f:
    urls_content = f.read()

old_import = '    WhatsAppMediaProxyView,'
new_import = '''    WhatsAppMediaProxyView,
    WhatsAppProfilePicView,'''
urls_content = urls_content.replace(old_import, new_import)

old_path = '    path("media-proxy/", WhatsAppMediaProxyView.as_view(), name="whatsapp-media-proxy"),'
new_path = '''    path("media-proxy/", WhatsAppMediaProxyView.as_view(), name="whatsapp-media-proxy"),
    path("profile-pic/<str:chat_id>/", WhatsAppProfilePicView.as_view(), name="whatsapp-profile-pic"),'''
urls_content = urls_content.replace(old_path, new_path)

with open('whatsapp/urls.py', 'w', encoding='utf-8') as f:
    f.write(urls_content)
print('Added profile pic URL')
