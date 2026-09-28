with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix profile pic endpoint
old_profile_pic_url = '''        # Construct the URL to get the profile pic
        url = f"{waha_url}/api/{session}/contacts/{chat_id}/profile-picture"'''
new_profile_pic_url = '''        # Correct WAHA endpoint for profile pictures
        import urllib.parse
        url = f"{waha_url}/api/contacts/profile-picture?session={urllib.parse.quote(session)}&contactId={urllib.parse.quote(chat_id)}"'''
content = content.replace(old_profile_pic_url, new_profile_pic_url)

# Fix contact info endpoint
old_contact_url = '''        url = f"{waha_url}/api/{session}/contacts/{chat_id}"'''
new_contact_url = '''        import urllib.parse as _parse
        url = f"{waha_url}/api/contacts?session={_parse.quote(session)}&contactId={_parse.quote(chat_id)}"'''
content = content.replace(old_contact_url, new_contact_url)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed WAHA API endpoints')
