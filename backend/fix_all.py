with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove RefreshCw and MoreVertical from sidebar header
old_sidebar_buttons = '''          <div className="flex gap-4 text-slate-500">
            <RefreshCw 
              className={w-5 h-5 cursor-pointer hover:text-slate-700 } 
              onClick={fetchConversations}
            />
            <MoreVertical className="w-5 h-5 cursor-pointer hover:text-slate-700" />
          </div>'''
new_sidebar_buttons = '''          <div className="flex gap-4 text-slate-500">
          </div>'''
content = content.replace(old_sidebar_buttons, new_sidebar_buttons)

# Fix 2: Enhance company lookup - use wahaContact resolved phone to look up prospect
# Replace: {selectedChat.prospect_name || 'N/A'}
# With: logic that also looks in whatsapp_name or contact_name for matching
old_company = '''<p className="text-slate-800 mt-1">{selectedChat.prospect_name || 'N/A'}</p>'''
new_company = '''<p className="text-slate-800 mt-1">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Not linked to CRM'}</p>'''
content = content.replace(old_company, new_company)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Applied frontend fixes')
