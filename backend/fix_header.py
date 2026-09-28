with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_header_text = '''                <div>
                  <h2 className="font-semibold text-slate-800">{selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact"}</h2>
                  <p className="text-xs text-slate-500 font-medium">{selectedChat.prospect_name || 'Unknown Company'}</p>
                </div>'''

new_header_text = '''                <div>
                  <h2 className="font-semibold text-slate-800">{(wahaContact && wahaContact.pushname) ? wahaContact.pushname : (selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact")}</h2>
                  <p className="text-xs text-slate-500 font-medium">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Unknown Company'}</p>
                </div>'''

content = content.replace(old_header_text, new_header_text)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated chat header')
