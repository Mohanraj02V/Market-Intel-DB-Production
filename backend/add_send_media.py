with open('whatsapp/views.py', 'r') as f:
    content = f.read()

# Add WhatsAppSendMediaView
send_media_view = '''

class WhatsAppSendMediaView(APIView):
    """
    Send a media file (image, document, audio, video) via WhatsApp.
    Accepts multipart/form-data with the file and optional caption.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import base64
        import os
        import urllib.request
        import json as _json

        chat_id = request.data.get("chat_id")
        caption = request.data.get("caption", "")
        uploaded_file = request.FILES.get("file")

        if not chat_id or not uploaded_file:
            return Response({"detail": "chat_id and file are required."}, status=400)

        file_bytes = uploaded_file.read()
        mime = uploaded_file.content_type or "application/octet-stream"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        # Choose endpoint based on MIME type
        if mime.startswith("image/"):
            endpoint = "sendImage"
        elif mime.startswith("audio/"):
            endpoint = "sendVoice"
        else:
            endpoint = "sendFile"

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session = "mohan"

        payload = _json.dumps({
            "session": session,
            "chatId": chat_id,
            "file": {
                "mimetype": mime,
                "data": data_uri,
                "filename": uploaded_file.name,
            },
            "caption": caption,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{waha_url}/api/{session}/{endpoint}",
            data=payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                waha_data = _json.loads(resp.read().decode("utf-8"))
                return Response({"status": "sent", "waha_response": waha_data}, status=200)
        except Exception as e:
            logger.error("Failed to send media via WAHA: %s", e)
            return Response({"detail": f"Failed to send media: {e}"}, status=502)
'''

content = content.rstrip() + send_media_view
with open('whatsapp/views.py', 'w') as f:
    f.write(content)
print('Done!')
