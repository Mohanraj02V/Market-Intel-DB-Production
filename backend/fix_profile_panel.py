with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: formatPhoneFromChatId to handle @s.whatsapp.net  
old_formatter = '''  const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us')) {
      return '+' + chatId.split('@')[0];
    }
    return ''; // hide @lid
  };'''

new_formatter = '''  const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us') || chatId.includes('@s.whatsapp.net')) {
      return '+' + chatId.split('@')[0];
    }
    return '';
  };'''

content = content.replace(old_formatter, new_formatter)

# Fix 2: Profile image - use wahaContact.id (which is the @c.us form) when available
old_img = '''<img src={"http://localhost:8000/api/whatsapp/profile-pic/" + selectedChat.chat_id + "/"} className="w-full h-full object-cover relative z-10" onError={(e) => e.target.style.display = 'none'} />
              <span className="absolute z-0">{selectedChat.prospect_name ? selectedChat.prospect_name.charAt(0) : selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}</span>'''

new_img = '''<img src={"http://localhost:8000/api/whatsapp/profile-pic/" + (wahaContact && wahaContact.id ? wahaContact.id : selectedChat.chat_id) + "/"} className="w-full h-full object-cover relative z-10" onError={(e) => e.target.style.display = 'none'} />
              <span className="absolute inset-0 flex items-center justify-center">{selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}</span>'''

content = content.replace(old_img, new_img)

# Fix 3: Name - use wahaContact.pushname if we have it
old_h3 = '''<h3 className="text-xl font-bold text-slate-800 text-center">{selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact"}</h3>
            <p className="text-slate-500 text-sm mt-1">{formatPhoneFromChatId(selectedChat.chat_id) ? formatPhoneFromChatId(selectedChat.chat_id) : selectedChat.prospect_phone ? selectedChat.prospect_phone : (wahaContact?.phoneNumber ? formatPhoneFromChatId(wahaContact.phoneNumber) : "Phone hidden")}</p>'''

new_h3 = '''<h3 className="text-xl font-bold text-slate-800 text-center">{(wahaContact && wahaContact.pushname) ? wahaContact.pushname : (selectedChat.contact_name || "Unknown Contact")}</h3>
            <p className="text-slate-500 text-sm mt-1 font-mono">{formatPhoneFromChatId(selectedChat.chat_id) || (wahaContact && wahaContact.phoneNumber ? formatPhoneFromChatId(wahaContact.phoneNumber) : '') || selectedChat.prospect_phone || 'Loading...'}</p>'''

content = content.replace(old_h3, new_h3)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done fixing profile panel')
