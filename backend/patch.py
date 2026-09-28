with open('whatsapp/webhooks.py', 'r') as f:
    content = f.read()

import_target = 'import json\nimport logging'
import_replacement = '''import json
import logging
import urllib.request
import urllib.error
import urllib.parse
import mimetypes
import os
from django.core.files.base import ContentFile

def _download_and_save_media_bg(message_id, session_name: str):
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
        api_key = os.getenv('WHATSAPP_API_KEY')
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
        logging.getLogger(__name__).error('Failed to download media for message %s: %s', wa_message.waha_message_id, e)
'''

content = content.replace(import_target, import_replacement)
content = content.replace('import json\r\nimport logging', import_replacement)

logic_target = '''        event_record.whatsapp_message = wa_message\n        event_record.save(update_fields=["whatsapp_message"])\n\n    _write_audit_log('''
logic_replacement = '''        event_record.whatsapp_message = wa_message\n        event_record.save(update_fields=["whatsapp_message"])\n\n    if event_data.get("hasMedia") and wa_message.waha_message_id:\n        import threading\n        threading.Thread(target=_download_and_save_media_bg, args=(wa_message.pk, session_name)).start()\n\n    _write_audit_log('''

content = content.replace(logic_target, logic_replacement)

logic_target_win = '''        event_record.whatsapp_message = wa_message\r\n        event_record.save(update_fields=["whatsapp_message"])\r\n\r\n    _write_audit_log('''
logic_replacement_win = '''        event_record.whatsapp_message = wa_message\r\n        event_record.save(update_fields=["whatsapp_message"])\r\n\r\n    if event_data.get("hasMedia") and wa_message.waha_message_id:\r\n        import threading\r\n        threading.Thread(target=_download_and_save_media_bg, args=(wa_message.pk, session_name)).start()\r\n\r\n    _write_audit_log('''

content = content.replace(logic_target_win, logic_replacement_win)

with open('whatsapp/webhooks.py', 'w') as f:
    f.write(content)
