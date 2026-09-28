with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix conversation list avatar - replace the static initial letter with an img+fallback
old_list_avatar = '''                <div className="w-12 h-12 rounded-full bg-blue-100 flex-shrink-0 flex items-center justify-center text-blue-600 font-bold">
                  {chat.contact_name ? chat.contact_name.charAt(0) : '#'}
                </div>'''
new_list_avatar = '''                <div className="w-12 h-12 rounded-full bg-blue-100 flex-shrink-0 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={"http://localhost:8000/api/whatsapp/profile-pic/" + chat.chat_id + "/"}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{chat.contact_name ? chat.contact_name.charAt(0).toUpperCase() : '#'}</span>
                </div>'''
content = content.replace(old_list_avatar, new_list_avatar)

# Fix chat header avatar
old_header_avatar = '''                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold">
                  {selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}
                </div>'''
new_header_avatar = '''                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={"http://localhost:8000/api/whatsapp/profile-pic/" + selectedChat.chat_id + "/"}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{selectedChat.contact_name ? selectedChat.contact_name.charAt(0).toUpperCase() : '#'}</span>
                </div>'''
content = content.replace(old_header_avatar, new_header_avatar)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

# verify
with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    v = f.read()
print('list avatar fixed:', 'chat.chat_id + "/"' in v)
print('header avatar fixed:', 'selectedChat.chat_id + "/"' in v)
