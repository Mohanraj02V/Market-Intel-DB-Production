with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_call_icons = '''                <Video className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => alert('Video calls are not supported by the WAHA API yet.')} />
                <Phone className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => alert('Voice calls are not supported by the WAHA API yet.')} />'''

new_call_icons = ''''''

content = content.replace(old_call_icons, new_call_icons)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Removed call icons')
