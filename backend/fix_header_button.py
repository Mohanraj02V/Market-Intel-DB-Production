with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_header = '''                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
              </div>
            </div>'''

new_header = '''                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
                <button 
                  onClick={() => setShowProfilePanel(!showProfilePanel)}
                  className="text-slate-500 hover:text-slate-700 font-semibold text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-full transition-colors ml-2"
                >
                  View Profile
                </button>
              </div>
            </div>'''

if 'View Profile' not in content:
    content = content.replace(old_header, new_header)
    with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added explicit View Profile button')
