with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Fix header phone
old_header_phone = '''                  <h2 className="font-semibold text-slate-800">
                    {selectedChat.contact_name 
                      ? (formatPhoneFromChatId(selectedChat.chat_id) ? \\ (\)\ : selectedChat.contact_name)
                      : (formatPhoneFromChatId(selectedChat.chat_id) || 'Unknown Contact')}
                  </h2>'''
# I need to use regex because the backticks might have been stripped or evaluated differently, wait, I can just find the part that prints 'Unknown Contact' and replace the whole block.
content = re.sub(
    r'<h2 className="font-semibold text-slate-800">.*?</h2>',
    r'<h2 className="font-semibold text-slate-800">{selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact"}</h2>',
    content,
    flags=re.DOTALL
)

# Fix profile panel name
content = re.sub(
    r'<h3 className="text-xl font-bold text-slate-800 text-center">.*?</h3>',
    r'<h3 className="text-xl font-bold text-slate-800 text-center">{selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact"}</h3>',
    content,
    flags=re.DOTALL
)

# Fix profile panel phone
content = re.sub(
    r'<p className="text-slate-500 text-sm mt-1">\{formatPhoneFromChatId\(selectedChat\.chat_id\).*?\}</p>',
    r'<p className="text-slate-500 text-sm mt-1">{formatPhoneFromChatId(selectedChat.chat_id) ? "+" + formatPhoneFromChatId(selectedChat.chat_id) : selectedChat.prospect_phone ? selectedChat.prospect_phone : "Phone hidden"}</p>',
    content
)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated UI to use prospect_phone')
