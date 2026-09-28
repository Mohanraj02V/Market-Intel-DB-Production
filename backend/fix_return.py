with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_return = '''        return Response({"status": "sent", "waha_response": waha_data}, status=200)'''

new_return = '''        from .serializers import WhatsAppMessageSerializer
        msg_data = WhatsAppMessageSerializer(wa_msg).data if 'wa_msg' in locals() else None
        return Response(msg_data or {"status": "sent", "waha_response": waha_data}, status=200)'''

content = content.replace(old_return, new_return)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed backend return value:', new_return[:50] in content)
