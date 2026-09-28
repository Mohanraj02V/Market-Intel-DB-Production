with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add state for chat message search
old_state = '''  const [searchQuery, setSearchQuery] = useState('');'''
new_state = '''  const [searchQuery, setSearchQuery] = useState('');
  const [showMsgSearch, setShowMsgSearch] = useState(false);
  const [msgSearchQuery, setMsgSearchQuery] = useState('');'''
content = content.replace(old_state, new_state)

# 2. Add onClick to search icon in header
old_search_icon = '''<Search className="w-5 h-5 cursor-pointer hover:text-slate-700" />'''
new_search_icon = '''<Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />'''
content = content.replace(old_search_icon, new_search_icon)

# 3. Add call onClick alerts
old_call_icons = '''                <Video className="w-5 h-5 cursor-pointer hover:text-slate-700" />
                <Phone className="w-5 h-5 cursor-pointer hover:text-slate-700" />'''
new_call_icons = '''                <Video className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => alert('Video calls are not supported by the WAHA API yet.')} />
                <Phone className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => alert('Voice calls are not supported by the WAHA API yet.')} />'''
content = content.replace(old_call_icons, new_call_icons)

# 4. Add the message search bar UI below header and filter messages
old_messages_container = '''            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loadingMessages ? ('''

new_messages_container = '''            {/* Message Search Bar */}
            {showMsgSearch && (
              <div className="px-4 py-2 border-b bg-slate-50 flex items-center gap-2">
                <Search className="w-4 h-4 text-slate-400" />
                <input 
                  type="text" 
                  autoFocus
                  placeholder="Search messages..." 
                  value={msgSearchQuery}
                  onChange={(e) => setMsgSearchQuery(e.target.value)}
                  className="w-full bg-transparent border-none text-sm focus:outline-none"
                />
                <button onClick={() => { setShowMsgSearch(false); setMsgSearchQuery(''); }} className="text-slate-400 hover:text-slate-600 text-sm">Cancel</button>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loadingMessages ? ('''

content = content.replace(old_messages_container, new_messages_container)

# 5. Apply the filter to the messages map
old_messages_map = '''              ) : (
                messages.map(msg => {'''
new_messages_map = '''              ) : (
                messages.filter(msg => {
                  if (!msgSearchQuery) return true;
                  const text = (msg.full_body || msg.body_preview || '').toLowerCase();
                  return text.includes(msgSearchQuery.toLowerCase());
                }).map(msg => {'''
content = content.replace(old_messages_map, new_messages_map)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Applied chat search UI')
