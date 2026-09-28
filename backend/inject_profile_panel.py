with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_end = '''    </div>
  );
}'''

new_end = '''      {/* Contact Profile Panel */}
      {selectedChat && showProfilePanel && (
        <div className="w-80 border-l border-slate-200 bg-white flex flex-col flex-shrink-0 animate-in slide-in-from-right overflow-y-auto">
          <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
            <h2 className="font-semibold text-slate-800">Contact Info</h2>
            <button onClick={() => setShowProfilePanel(false)} className="text-slate-400 hover:text-slate-600 text-xl font-bold">&times;</button>
          </div>
          
          <div className="p-6 flex flex-col items-center border-b border-slate-100">
            <div className="w-32 h-32 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-4xl mb-4 overflow-hidden relative shadow-sm">
              <img src={http://localhost:8000/api/whatsapp/profile-pic//} className="w-full h-full object-cover" onError={(e) => e.target.style.display = 'none'} />
              <span className="absolute z-[-1]">{selectedChat.prospect_name ? selectedChat.prospect_name.charAt(0) : selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}</span>
            </div>
            <h3 className="text-xl font-bold text-slate-800 text-center">
              {selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || 'Unknown Contact'}
            </h3>
            <p className="text-slate-500 text-sm mt-1">{formatPhoneFromChatId(selectedChat.chat_id) ? + : 'Phone hidden'}</p>
          </div>

          <div className="p-4 space-y-4">
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Company</label>
              <p className="text-slate-800 mt-1">{selectedChat.prospect_name || 'N/A'}</p>
            </div>
            
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chat ID</label>
              <p className="text-slate-800 mt-1 text-sm break-all">{selectedChat.chat_id}</p>
            </div>
            
            <div>
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}'''

content = content.replace(old_end, new_end)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Injected profile panel')
