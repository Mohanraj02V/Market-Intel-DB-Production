with open('whatsapp/models.py', 'r') as f:
    content = f.read()

target = '''    # Media support
    has_media = models.BooleanField(default=False)
    media_file = models.FileField(upload_to="whatsapp_media/%Y/%m/", null=True, blank=True)
    media_mime_type = models.CharField(max_length=100, null=True, blank=True)'''

replacement = '''    # Media support
    has_media = models.BooleanField(default=False)
    media_file = models.FileField(upload_to="whatsapp_media/%Y/%m/", null=True, blank=True)
    media_mime_type = models.CharField(max_length=100, null=True, blank=True)
    # Direct media URL from WAHA (e.g. http://localhost:3000/api/files/session/file.jpeg)
    media_url = models.URLField(max_length=1000, null=True, blank=True)'''

content = content.replace(target, replacement)
with open('whatsapp/models.py', 'w') as f:
    f.write(content)
print('Done!')
