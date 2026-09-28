with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_sidebar = '''          <div className="flex gap-4 text-slate-500">
            <RefreshCw 
              className={w-5 h-5 cursor-pointer hover:text-slate-700 } 
              onClick={fetchConversations}
            />
            <MoreVertical className="w-5 h-5 cursor-pointer hover:text-slate-700" />
          </div>
        </div>'''
new_sidebar = '''          <div className="flex gap-4 text-slate-500">
          </div>
        </div>'''
content = content.replace(old_sidebar, new_sidebar)

old_chat = '''              <div className="flex gap-4 text-slate-500 items-center">
                <button 
                  onClick={handleSyncHistory}
                  title="Sync History from Phone"
                  className="p-1.5 hover:bg-slate-100 rounded-md transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>

                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
                <MoreVertical className="w-5 h-5 cursor-pointer hover:text-slate-700" />
              </div>
            </div>'''
new_chat = '''              <div className="flex gap-4 text-slate-500 items-center">
                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
              </div>
            </div>'''
content = content.replace(old_chat, new_chat)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Removed icons')
