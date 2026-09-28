with open('whatsapp/webhooks.py', 'r') as f:
    content = f.read()

content = content.replace("WHATSAPP_API_KEY", "WHATSAPP_SERVICE_API_KEY")

with open('whatsapp/webhooks.py', 'w') as f:
    f.write(content)
print('Patched successfully!')
