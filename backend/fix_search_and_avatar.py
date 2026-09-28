with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add searchQuery state
old_state = '''  const [showEmojiPicker, setShowEmojiPicker] = useState(false);'''
new_state = '''  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');'''
content = content.replace(old_state, new_state)

# Add search input handling
old_search_input = '''              <input 
                type="text" 
                placeholder="Search or start new chat" 
                className="w-full pl-10 pr-4 py-2 bg-slate-100 border-none rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />'''
new_search_input = '''              <input 
                type="text" 
                placeholder="Search chats..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-slate-100 border-none rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />'''
content = content.replace(old_search_input, new_search_input)

# Filter chats logic
old_chat_map = '''            {chats.map(c => ('''
new_chat_map = '''            {chats.filter(c => {
              const term = searchQuery.toLowerCase();
              const name = (c.prospect_name || c.contact_name || c.whatsapp_name || c.chat_id || '').toLowerCase();
              return name.includes(term);
            }).map(c => ('''
content = content.replace(old_chat_map, new_chat_map)

# Replace avatar logic in chat list
old_avatar1 = '''                <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-sm shrink-0">
                  {c.prospect_name ? c.prospect_name.charAt(0) : c.contact_name ? c.contact_name.charAt(0) : '#'}
                </div>'''
new_avatar1 = '''                <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-sm shrink-0 overflow-hidden relative">
                  <img src={http://localhost:8000/api/whatsapp/profile-pic//} className="w-full h-full object-cover" onError={(e) => e.target.style.display = 'none'} />
                  <span className="absolute z-[-1]">{c.prospect_name ? c.prospect_name.charAt(0) : c.contact_name ? c.contact_name.charAt(0) : '#'}</span>
                </div>'''
content = content.replace(old_avatar1, new_avatar1)

# Replace avatar logic in header
old_avatar2 = '''              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-sm">
                  {selectedChat.prospect_name ? selectedChat.prospect_name.charAt(0) : selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : 'M'}
                </div>'''
new_avatar2 = '''              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-sm overflow-hidden relative">
                  <img src={http://localhost:8000/api/whatsapp/profile-pic//} className="w-full h-full object-cover" onError={(e) => e.target.style.display = 'none'} />
                  <span className="absolute z-[-1]">{selectedChat.prospect_name ? selectedChat.prospect_name.charAt(0) : selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}</span>
                </div>'''
content = content.replace(old_avatar2, new_avatar2)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Applied frontend fixes')
