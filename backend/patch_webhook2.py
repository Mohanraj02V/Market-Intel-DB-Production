with open('whatsapp/webhooks.py', 'r') as f:
    content = f.read()

# Fix 1: Update the media download function to use the direct WAHA file URL stored in the webhook payload
# instead of trying to re-download it.

old_func = '''def _download_and_save_media_bg(message_id, session_name: str):
    from whatsapp.models import WhatsAppMessage
    import logging
    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return
        
    waha_url = os.getenv('WAHA_API_URL', 'http://localhost:3000')
    url = f'{waha_url}/api/messages/{wa_message.waha_message_id}/download?session={urllib.parse.quote(session_name)}'
    
    try:
        req = urllib.request.Request(url)
        api_key = os.getenv('WHATSAPP_SERVICE_API_KEY')
        if api_key:
            req.add_header('X-Api-Key', api_key)
            
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
            content_type = response.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0]) or '.bin'
            file_name = f'{wa_message.waha_message_id}{ext}'
            
            wa_message.has_media = True
            wa_message.media_mime_type = content_type
            wa_message.media_file.save(file_name, ContentFile(content), save=True)
            logging.getLogger(__name__).info('Successfully downloaded media for %s', wa_message.waha_message_id)
    except Exception as e:
        logging.getLogger(__name__).error('Failed to download media for message %s: %s', wa_message.waha_message_id, e)'''

new_func = '''def _save_media_url_to_message(message_id, media_url: str, mime_type: str):
    """Store WAHA's local media URL directly in the database - no re-download needed."""
    from whatsapp.models import WhatsAppMessage
    import logging as _logging
    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return

    try:
        wa_message.has_media = True
        wa_message.media_mime_type = mime_type or ''
        wa_message.media_url = media_url
        wa_message.save(update_fields=['has_media', 'media_mime_type', 'media_url'])
        _logging.getLogger(__name__).info('Saved media URL for message %s: %s', wa_message.waha_message_id, media_url)
    except Exception as e:
        _logging.getLogger(__name__).error('Failed to save media URL for message %s: %s', wa_message.waha_message_id, e)


def _download_and_save_media_bg(message_id, session_name: str, media_url: str = None, mime_type: str = None):
    """Download media from WAHA and store it, or just store the URL if already provided."""
    from whatsapp.models import WhatsAppMessage
    import logging as _logging
    
    # If WAHA already gave us a URL, just store it directly
    if media_url:
        _save_media_url_to_message(message_id, media_url, mime_type)
        return
    
    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return
        
    waha_url = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000')
    url = f'{waha_url}/api/messages/{wa_message.waha_message_id}/download?session={urllib.parse.quote(session_name)}'
    
    try:
        req = urllib.request.Request(url)
        api_key = os.getenv('WHATSAPP_SERVICE_API_KEY')
        if api_key:
            req.add_header('X-Api-Key', api_key)
            
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
            content_type = response.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0]) or '.bin'
            file_name = f'{wa_message.waha_message_id}{ext}'
            
            wa_message.has_media = True
            wa_message.media_mime_type = content_type
            wa_message.media_file.save(file_name, ContentFile(content), save=True)
            _logging.getLogger(__name__).info('Successfully downloaded media for %s', wa_message.waha_message_id)
    except Exception as e:
        _logging.getLogger(__name__).error('Failed to download media for message %s: %s', wa_message.waha_message_id, e)'''

content = content.replace(old_func, new_func)

# Fix 2: Update the trigger to pass the media URL from the webhook payload
old_trigger = '''    if event_data.get("hasMedia") and wa_message.waha_message_id:
        import threading
        threading.Thread(target=_download_and_save_media_bg, args=(wa_message.pk, session_name)).start()'''

new_trigger = '''    if event_data.get("hasMedia") and wa_message.waha_message_id:
        import threading
        _media_info = event_data.get("media") or {}
        _media_url = _media_info.get("url") or None
        _mime_type = _media_info.get("mimetype") or None
        threading.Thread(
            target=_download_and_save_media_bg,
            args=(wa_message.pk, session_name, _media_url, _mime_type)
        ).start()'''

content = content.replace(old_trigger, new_trigger)

with open('whatsapp/webhooks.py', 'w') as f:
    f.write(content)
print('Done!')
