with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_badge = '''            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Matched Lead</label>
              <p className="mt-1">
                {selectedChat.is_matched ? (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    Yes (CRM Synced)
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-800">
                    Unmatched
                  </span>
                )}
              </p>
            </div>'''
            
new_badge = '''            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Matched Lead</label>
              <p className="mt-1">
                {selectedChat.is_matched || (wahaContact && wahaContact.company) ? (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    Yes (CRM Synced)
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-800">
                    Unmatched
                  </span>
                )}
              </p>
            </div>'''

content = content.replace(old_badge, new_badge)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated matched lead badge')
