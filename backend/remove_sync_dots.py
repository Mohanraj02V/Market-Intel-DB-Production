with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Sidebar icons
old_sidebar_icons = '''            <div className="flex gap-2 text-slate-500">
              <RefreshCw className="w-4 h-4 cursor-pointer hover:text-slate-700" onClick={() => fetchConversations()} />
              <MoreVertical className="w-4 h-4 cursor-pointer hover:text-slate-700" />
            </div>'''
new_sidebar_icons = '''            <div className="flex gap-2 text-slate-500">
            </div>'''
content = content.replace(old_sidebar_icons, new_sidebar_icons)

# Chat header icons
old_chat_icons = '''              <div className="flex gap-4 text-slate-500 items-center">
                <button 
                  onClick={handleSyncHistory}
                  title="Sync History from Phone"
                  className="p-1.5 hover:bg-slate-100 rounded-md transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                
                
                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
                <MoreVertical className="w-5 h-5 cursor-pointer hover:text-slate-700" />
              </div>'''
new_chat_icons = '''              <div className="flex gap-4 text-slate-500 items-center">
                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
              </div>'''
content = content.replace(old_chat_icons, new_chat_icons)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Removed sync and three-dot buttons')
