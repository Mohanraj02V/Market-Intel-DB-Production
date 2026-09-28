with open('whatsapp/webhooks.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''    # If WAHA already gave us a URL, just store it directly
    if media_url:
        _save_media_url_to_message(message_id, media_url, mime_type)
        return
    
    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return
        
    waha_url = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000')
    url = f'{waha_url}/api/messages/{wa_message.waha_message_id}/download?session={urllib.parse.quote(session_name)}'
    
    try:'''

new_func = '''    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return
        
    waha_url = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000')
    
    # Prioritize the direct media_url if provided, otherwise fallback to the download endpoint
    url = media_url if media_url else f'{waha_url}/api/messages/{wa_message.waha_message_id}/download?session={urllib.parse.quote(session_name)}'
    
    try:'''

content = content.replace(old_func, new_func)

with open('whatsapp/webhooks.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated media download to save to db')
