with open('whatsapp/urls.py', 'r') as f:
    content = f.read()

old_import = '    WhatsAppWebhookView,'
new_import = '''    WhatsAppSendMediaView,
    WhatsAppWebhookView,'''
content = content.replace(old_import, new_import)

old_send = '    path("send/", WhatsAppSendMessageView.as_view(), name="whatsapp-send"),'
new_send = '''    path("send/", WhatsAppSendMessageView.as_view(), name="whatsapp-send"),
    path("send-media/", WhatsAppSendMediaView.as_view(), name="whatsapp-send-media"),'''
content = content.replace(old_send, new_send)

with open('whatsapp/urls.py', 'w') as f:
    f.write(content)
print('Done!')
