with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update imports to add useRef and useCallback
old_import = "import React, { useState, useEffect, useRef } from 'react';"
new_import = "import React, { useState, useEffect, useRef, useCallback } from 'react';"
content = content.replace(old_import, new_import)

# 2. Add new state variables after existing state
old_state = """  const [toastMessage, setToastMessage] = useState(null);
  const messagesEndRef = useRef(null);"""
new_state = """  const [toastMessage, setToastMessage] = useState(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [attachPreview, setAttachPreview] = useState(null); // { file, url, mime }
  const [isSendingMedia, setIsSendingMedia] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const emojiPickerRef = useRef(null);"""
content = content.replace(old_state, new_state)

# 3. Add helper functions after handleKeyPress
old_scroll = """  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
  };"""
new_scroll = """  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
  };

  const handleEmojiClick = (emoji) => {
    setMessage(prev => prev + emoji);
    setShowEmojiPicker(false);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setAttachPreview({ file, url, mime: file.type });
    e.target.value = '';
  };

  const handleSendMedia = async () => {
    if (!attachPreview || !selectedChat) return;
    setIsSendingMedia(true);
    try {
      const formData = new FormData();
      formData.append('file', attachPreview.file);
      formData.append('chat_id', selectedChat.chat_id);
      if (message.trim()) formData.append('caption', message.trim());

      await api.post('/whatsapp/send-media/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setAttachPreview(null);
      setMessage('');
      setToastMessage({ text: 'Media sent!', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);
      setTimeout(() => fetchMessages(selectedChat.id), 2000);
    } catch (err) {
      setToastMessage({ text: err.response?.data?.detail || 'Failed to send media', type: 'error' });
      setTimeout(() => setToastMessage(null), 4000);
    } finally {
      setIsSendingMedia(false);
    }
  };

  // Common emoji set
  const EMOJIS = [
    '??','??','??','??','??','??','??','??','??','??',
    '??','??','??','??','??','??','??','??','??','??',
    '??','??','??','??','?','??','??','??','??','?',
    '??','??','??','??','??','??','??','??','??','??',
    '??','??','??','??','??','??','??','?','??','??',
  ];"""
content = content.replace(old_scroll, new_scroll)

# 4. Replace the input area
old_input = """            {/* Input Area */}
            <div className="p-3 bg-slate-100 flex items-center gap-3">
              <Smile className="w-6 h-6 text-slate-500 cursor-pointer hover:text-slate-700" />
              <Paperclip className="w-6 h-6 text-slate-500 cursor-pointer hover:text-slate-700" />
              <input 
                type="text" 
                placeholder="Type a message" 
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyPress}
                className="flex-1 bg-white border-none rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 shadow-sm"
              />
              {message.trim() ? (
                <div 
                  onClick={handleSendMessage}
                  className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center cursor-pointer hover:bg-green-600 transition shadow-sm"
                >
                  <Send className="w-5 h-5 text-white ml-1" />
                </div>
              ) : null}
            </div>"""

new_input = """            {/* Input Area */}
            <div className="relative">
              {/* Emoji Picker */}
              {showEmojiPicker && (
                <div className="absolute bottom-16 left-2 z-50 bg-white border border-slate-200 rounded-xl shadow-xl p-3 w-72">
                  <div className="grid grid-cols-10 gap-1 max-h-40 overflow-y-auto">
                    {EMOJIS.map(emoji => (
                      <button
                        key={emoji}
                        onClick={() => handleEmojiClick(emoji)}
                        className="text-xl hover:bg-slate-100 rounded p-0.5 transition"
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Attach Preview */}
              {attachPreview && (
                <div className="absolute bottom-16 left-0 right-0 bg-white border-t border-slate-200 p-3 flex items-center gap-3 shadow-md">
                  {attachPreview.mime.startsWith('image/') ? (
                    <img src={attachPreview.url} alt="Preview" className="h-20 w-20 object-cover rounded-lg border" />
                  ) : (
                    <div className="h-20 w-20 bg-slate-100 rounded-lg border flex flex-col items-center justify-center text-xs text-slate-600 p-1 text-center">
                      <Paperclip className="w-6 h-6 mb-1" />
                      <span className="truncate w-full text-center">{attachPreview.file.name}</span>
                    </div>
                  )}
                  <div className="flex-1">
                    <p className="text-xs text-slate-500">{attachPreview.file.name}</p>
                    <p className="text-xs text-slate-400">{(attachPreview.file.size / 1024).toFixed(1)} KB</p>
                    <input
                      type="text"
                      placeholder="Add a caption..."
                      value={message}
                      onChange={e => setMessage(e.target.value)}
                      className="mt-1 w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <button onClick={() => { setAttachPreview(null); setMessage(''); }} className="text-xs text-red-500 hover:text-red-700">Remove</button>
                    <button
                      onClick={handleSendMedia}
                      disabled={isSendingMedia}
                      className="bg-green-500 text-white text-xs px-3 py-1.5 rounded-lg hover:bg-green-600 disabled:opacity-50"
                    >
                      {isSendingMedia ? 'Sending...' : 'Send'}
                    </button>
                  </div>
                </div>
              )}

              {/* Hidden file input */}
              <input ref={fileInputRef} type="file" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx" className="hidden" onChange={handleFileSelect} />

              <div className="p-3 bg-slate-100 flex items-center gap-3">
                <button onClick={() => setShowEmojiPicker(p => !p)} className="text-slate-500 hover:text-slate-700 transition">
                  <Smile className="w-6 h-6" />
                </button>
                <button onClick={() => fileInputRef.current?.click()} className="text-slate-500 hover:text-slate-700 transition">
                  <Paperclip className="w-6 h-6" />
                </button>
                <input 
                  type="text" 
                  placeholder="Type a message" 
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  onFocus={() => setShowEmojiPicker(false)}
                  className="flex-1 bg-white border-none rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 shadow-sm"
                />
                {message.trim() && !attachPreview ? (
                  <div 
                    onClick={handleSendMessage}
                    className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center cursor-pointer hover:bg-green-600 transition shadow-sm"
                  >
                    <Send className="w-5 h-5 text-white ml-1" />
                  </div>
                ) : null}
              </div>
            </div>"""

content = content.replace(old_input, new_input)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
print('input replaced:', new_input[:50] in content)
