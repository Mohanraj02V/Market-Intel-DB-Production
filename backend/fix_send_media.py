with open('whatsapp/views.py', 'r') as f:
    content = f.read()

# Fix the endpoint URL - WAHA uses /api/sendImage not /api/{session}/sendImage
old = '''        req = urllib.request.Request(
            f"{waha_url}/api/{session}/{endpoint}",
            data=payload,
            method="POST",
        )'''

new = '''        req = urllib.request.Request(
            f"{waha_url}/api/{endpoint}",
            data=payload,
            method="POST",
        )'''

content = content.replace(old, new)

# Also fix: sendVoice is not a valid endpoint - use sendFile for audio too
old2 = '''        if mime.startswith("image/"):
            endpoint = "sendImage"
        elif mime.startswith("audio/"):
            endpoint = "sendVoice"
        else:
            endpoint = "sendFile"'''

new2 = '''        if mime.startswith("image/"):
            endpoint = "sendImage"
        elif mime.startswith("video/"):
            endpoint = "sendVideo"
        else:
            endpoint = "sendFile"'''

content = content.replace(old2, new2)

with open('whatsapp/views.py', 'w') as f:
    f.write(content)
print('Done!')
