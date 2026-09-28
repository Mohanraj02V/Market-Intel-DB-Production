import os, django, json, urllib.request, urllib.parse
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from whatsapp.models import WhatsAppMessage, WhatsAppConversation

API_KEY = os.getenv('WHATSAPP_SERVICE_API_KEY', '')
WAHA_URL = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000')

# Get all conversations and fetch their messages from WAHA
convs = WhatsAppConversation.objects.all()
updated = 0

for conv in convs:
    chat_id = conv.chat_id
    session = conv.session.session_name if conv.session else 'mohan'
    
    url = f"{WAHA_URL}/api/{session}/chats/{urllib.parse.quote(chat_id)}/messages?limit=50"
    req = urllib.request.Request(url)
    if API_KEY:
        req.add_header('X-Api-Key', API_KEY)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            messages = data if isinstance(data, list) else data.get('messages', data)
            
        for waha_msg in messages:
            if not waha_msg.get('hasMedia'):
                continue
            
            waha_id = waha_msg.get('id', '')
            media = waha_msg.get('media') or {}
            media_url = media.get('url')
            mime_type = media.get('mimetype', '')
            
            if not media_url or not waha_id:
                continue
            
            # Find matching DB message
            db_msg = WhatsAppMessage.objects.filter(
                waha_message_id=waha_id,
                conversation=conv
            ).first()
            
            if db_msg and not db_msg.media_url:
                db_msg.has_media = True
                db_msg.media_url = media_url
                db_msg.media_mime_type = mime_type
                db_msg.save(update_fields=['has_media', 'media_url', 'media_mime_type'])
                print(f"  Updated: {waha_id} -> {media_url}")
                updated += 1
    except Exception as e:
        print(f"Error for {chat_id}: {e}")

print(f"\nTotal updated: {updated} messages")
