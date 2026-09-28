with open('whatsapp/serializers.py', 'r') as f:
    content = f.read()

target = '''            "has_media",
            "media_file",
            "media_mime_type",'''

replacement = '''            "has_media",
            "media_file",
            "media_mime_type",
            "media_url",'''

content = content.replace(target, replacement)
with open('whatsapp/serializers.py', 'w') as f:
    f.write(content)
print('Done!')
