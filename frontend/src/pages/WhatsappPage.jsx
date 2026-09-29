import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Search, MoreVertical, Paperclip, Smile, Send, Phone, Video, RefreshCw } from 'lucide-react';
import api from '../services/api';

const API_BASE = api.defaults.baseURL;
const HOST_URL = API_BASE.endsWith('/api') ? API_BASE.slice(0, -4) : API_BASE;

export default function WhatsappPage() {
  const [chats, setChats] = useState([]);
  const [selectedChat, setSelectedChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showMsgSearch, setShowMsgSearch] = useState(false);
  const [showProfilePanel, setShowProfilePanel] = useState(false);
  const [wahaContact, setWahaContact] = useState(null);

  useEffect(() => {
    if (selectedChat) {
      setWahaContact(null);
      fetch(API_BASE + "/whatsapp/contact-info/" + selectedChat.chat_id + "/")
        .then(r => r.json())
        .then(data => {
            if (data.phoneNumber) {
                setWahaContact(data);
            }
        }).catch(err => console.error(err));
    }
  }, [selectedChat]);
  const [msgSearchQuery, setMsgSearchQuery] = useState('');
  const [attachPreview, setAttachPreview] = useState(null); // { file, url, mime }
  const [isSendingMedia, setIsSendingMedia] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const emojiPickerRef = useRef(null);

  useEffect(() => {
    fetchConversations();
  }, []);

  useEffect(() => {
    if (selectedChat) {
      fetchMessages(selectedChat.id);
    }
  }, [selectedChat]);

  const handleSyncHistory = async () => {
    if (!selectedChat) return;
    try {
      setToastMessage({ text: 'Syncing history...', type: 'info' });
      const response = await api.post(`/whatsapp/conversations/${selectedChat.id}/sync/`);
      setToastMessage({ text: response.data.detail || 'Sync complete.', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);
      fetchMessages(selectedChat.id);
    } catch (error) {
      console.error('Failed to sync history:', error);
      setToastMessage({ text: error.response?.data?.detail || 'Failed to sync history', type: 'error' });
      setTimeout(() => setToastMessage(null), 4000);
    }
  };

  // Polling for real-time updates
  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchConversations(true);
      if (selectedChat) {
        fetchMessages(selectedChat.id, true);
      }
    }, 5000); // Poll every 5 seconds
    return () => clearInterval(intervalId);
  }, [selectedChat]);

  // Scroll to bottom whenever messages load (chat switch or new message)
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(scrollToBottom, 50);
    }
  }, [messages.length, selectedChat?.id]);

  const fetchConversations = async (isPolling = false) => {
    try {
      const response = await api.get('/whatsapp/conversations/');
      setChats(response.data);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  const fetchMessages = async (conversationId, isPolling = false) => {
    if (!isPolling) setLoadingMessages(true);
    try {
      const response = await api.get(`/whatsapp/conversations/${conversationId}/messages/`);
      // Backend returns latest messages first, we want oldest first for chat display
      const sorted = response.data.messages.reverse();
      setMessages(sorted);
      if (!isPolling) setTimeout(scrollToBottom, 150);
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    } finally {
      if (!isPolling) setLoadingMessages(false);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim() || !selectedChat) return;
    
    const body = message.trim();
    setMessage('');
    
    try {
      const response = await api.post('/whatsapp/send/', {
        prospect_contact_id: selectedChat.prospect_contact || null,
        chat_id: selectedChat.chat_id,
        message_body: body
      });
      
      // Append the new message to the list
      setMessages([...messages, response.data]);
      setTimeout(scrollToBottom, 100);
      
      // Update the last message in the chat list
      setChats(prevChats => prevChats.map(c => 
        c.id === selectedChat.id 
          ? { ...c, last_message_preview: body, last_message_at: new Date().toISOString() } 
          : c
      ));
    } catch (error) {
      console.error('Failed to send message:', error);
      const errMsg = error.response?.data?.detail || 'Failed to send message';
      if (typeof errMsg === 'string') {
        setToastMessage({ text: errMsg, type: 'error' });
      } else {
        setToastMessage({ text: 'An error occurred while sending the message.', type: 'error' });
      }
      setTimeout(() => setToastMessage(null), 4000);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const scrollToBottom = () => {
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

      const response = await api.post('/whatsapp/send-media/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setAttachPreview(null);
      setMessage('');
      
      // Append the new message instantly if the backend returns it
      if (response.data && response.data.id) {
        setMessages(prev => [...prev, response.data]);
        setTimeout(scrollToBottom, 100);
      } else {
        setTimeout(() => fetchMessages(selectedChat.id), 1000);
      }
      
      setToastMessage({ text: 'Media sent!', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);
    } catch (err) {
      setToastMessage({ text: err.response?.data?.detail || 'Failed to send media', type: 'error' });
      setTimeout(() => setToastMessage(null), 4000);
    } finally {
      setIsSendingMedia(false);
    }
  };

  // Common emoji set
  const EMOJIS = [
    '😀','😂','😊','😍','🥰','😘','😎','🤔','😅','😭',
    '😱','🥳','🤗','😏','😒','🙄','😤','🤩','🥺','😔',
    '👍','👎','❤️','🔥','✅','🎉','👏','🙏','💯','⭐',
    '😴','🤤','😋','🤪','🤓','😷','🤒','🤢','😈','👻',
    '🌹','🌺','🌸','🌼','🌻','🌞','🌈','⚡','💧','🎵',
  ];

  const formatTime = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us') || chatId.includes('@s.whatsapp.net')) {
      return '+' + chatId.split('@')[0];
    }
    return '';
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`absolute top-4 right-4 z-50 p-4 rounded shadow-md flex items-center justify-between min-w-[300px] transition-all duration-300 border-l-4 ${
          toastMessage.type === 'error' ? 'bg-red-50 border-red-500' : 
          toastMessage.type === 'success' ? 'bg-green-50 border-green-500' : 
          'bg-blue-50 border-blue-500'
        }`}>
          <div className="flex items-center">
            <div className="py-1">
              {toastMessage.type === 'error' ? (
                <svg className="fill-current h-6 w-6 text-red-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11v4a1 1 0 11-2 0V7a1 1 0 112 0zm-1 8a1.5 1.5 0 110-3 1.5 1.5 0 010 3z"/></svg>
              ) : toastMessage.type === 'success' ? (
                <svg className="fill-current h-6 w-6 text-green-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"/></svg>
              ) : (
                <svg className="fill-current h-6 w-6 text-blue-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11v4a1 1 0 11-2 0V7a1 1 0 112 0zm-1 8a1.5 1.5 0 110-3 1.5 1.5 0 010 3z"/></svg>
              )}
            </div>
            <div>
              <p className={`font-semibold ${
                toastMessage.type === 'error' ? 'text-red-700' : 
                toastMessage.type === 'success' ? 'text-green-700' : 
                'text-blue-700'
              }`}>
                {toastMessage.type === 'error' ? 'Error' : toastMessage.type === 'success' ? 'Success' : 'Info'}
              </p>
              <p className={`text-sm ${
                toastMessage.type === 'error' ? 'text-red-600' : 
                toastMessage.type === 'success' ? 'text-green-600' : 
                'text-blue-600'
              }`}>{toastMessage.text}</p>
            </div>
          </div>
          <button onClick={() => setToastMessage(null)} className={`${
            toastMessage.type === 'error' ? 'text-red-500 hover:text-red-700' : 
            toastMessage.type === 'success' ? 'text-green-500 hover:text-green-700' : 
            'text-blue-500 hover:text-blue-700'
          }`}>
             <svg className="h-4 w-4 fill-current" role="button" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><title>Close</title><path d="M14.348 14.849a1.2 1.2 0 0 1-1.697 0L10 11.819l-2.651 3.029a1.2 1.2 0 1 1-1.697-1.697l2.758-3.15-2.759-3.152a1.2 1.2 0 1 1 1.697-1.697L10 8.183l2.651-3.031a1.2 1.2 0 1 1 1.697 1.697l-2.758 3.152 2.758 3.15a1.2 1.2 0 0 1 0 1.698z"/></svg>
          </button>
        </div>
      )}

      {/* Sidebar */}
      <div className="w-1/3 flex-shrink-0 border-r border-slate-200 flex flex-col bg-slate-50">
        <div className="p-4 bg-slate-100 border-b border-slate-200 flex justify-between items-center">
          <div className="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center text-white font-bold">
            LQ
          </div>
          <div className="flex gap-4 text-slate-500">
            <RefreshCw 
              className={`w-5 h-5 cursor-pointer hover:text-slate-700 ${loading ? 'animate-spin' : ''}`} 
              onClick={fetchConversations}
            />
            <MoreVertical className="w-5 h-5 cursor-pointer hover:text-slate-700" />
          </div>
        </div>
        <div className="p-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search or start new chat" 
              className="w-full bg-white border border-slate-200 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading && chats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">Loading conversations...</div>
          ) : chats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">No active conversations found.</div>
          ) : (
            chats.map(chat => (
              <div 
                key={chat.id} 
                onClick={() => setSelectedChat(chat)}
                className={`flex items-center gap-3 p-3 cursor-pointer hover:bg-slate-100 transition ${selectedChat?.id === chat.id ? 'bg-slate-100' : ''}`}
              >
                <div className="w-12 h-12 rounded-full bg-blue-100 flex-shrink-0 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={API_BASE + "/whatsapp/profile-pic/" + chat.chat_id + "/"}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{chat.contact_name ? chat.contact_name.charAt(0).toUpperCase() : '#'}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline mb-1">
                    <h3 className="font-semibold text-slate-800 truncate">
                      {chat.contact_name 
                        ? (formatPhoneFromChatId(chat.chat_id) ? `${chat.contact_name} (${formatPhoneFromChatId(chat.chat_id)})` : chat.contact_name)
                        : (formatPhoneFromChatId(chat.chat_id) || 'Unknown Contact')}
                    </h3>
                    <span className="text-xs text-slate-500">{formatTime(chat.last_message_at)}</span>
                  </div>
                  <div className="flex justify-between items-baseline">
                    <p className="text-sm text-slate-500 truncate">{chat.last_message_preview || 'No messages yet'}</p>
                    {chat.unread_count > 0 && (
                      <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center text-[10px] font-bold text-white">
                        {chat.unread_count}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-[#efeae2] min-w-0">
        {selectedChat ? (
          <>
            {/* Chat Header */}
            <div className="p-4 bg-white border-b border-slate-200 flex justify-between items-center z-10 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={API_BASE + "/whatsapp/profile-pic/" + selectedChat.chat_id + "/"}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{selectedChat.contact_name ? selectedChat.contact_name.charAt(0).toUpperCase() : '#'}</span>
                </div>
                <div>
                  <h2 className="font-semibold text-slate-800">{(wahaContact && wahaContact.pushname) ? wahaContact.pushname : (selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact")}</h2>
                  <p className="text-xs text-slate-500 font-medium">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Unknown Company'}</p>
                </div>
              </div>
              <div className="flex gap-4 text-slate-500 items-center">
                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
                <button 
                  onClick={() => setShowProfilePanel(!showProfilePanel)}
                  className="text-slate-500 hover:text-slate-700 font-semibold text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-full transition-colors ml-2"
                >
                  View Profile
                </button>
              </div>
            </div>

            {/* Message Search Bar */}
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
              {loadingMessages ? (
                <div className="flex justify-center p-4"><RefreshCw className="w-6 h-6 animate-spin text-slate-400" /></div>
              ) : messages.length === 0 ? (
                <div className="flex justify-center p-8 text-slate-500">No messages yet. Send the first message!</div>
              ) : (
                messages.filter(msg => {
                  if (!msgSearchQuery) return true;
                  const text = (msg.full_body || msg.body_preview || '').toLowerCase();
                  return text.includes(msgSearchQuery.toLowerCase());
                }).map(msg => {
                  const isMe = msg.direction === 'OUTBOUND';
                  const _rawMediaSrc = msg.media_url || msg.media_file || '';
                  let _proxySrc = '';
                  if (_rawMediaSrc) {
                    if (_rawMediaSrc.includes('localhost:3000')) {
                      _proxySrc = API_BASE + '/whatsapp/media-proxy/?url=' + encodeURIComponent(_rawMediaSrc);
                    } else if (_rawMediaSrc.startsWith('/')) {
                      _proxySrc = HOST_URL + _rawMediaSrc;
                    } else {
                      _proxySrc = _rawMediaSrc;
                    }
                  }
                  const _mime = msg.media_mime_type || '';
                  return (
                    <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[70%] rounded-lg p-3 ${isMe ? 'bg-[#d9fdd3] text-slate-800 rounded-tr-none' : 'bg-white text-slate-800 rounded-tl-none'} shadow-sm relative group`}>
                        {msg.has_media && _proxySrc && (
                          <div className="mb-2 group/media relative">
                            {!_proxySrc ? (
                              <div className="flex items-center justify-center p-4 bg-slate-100 rounded-md text-slate-500 text-sm">
                                <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Media Loading...
                              </div>
                            ) : _mime.startsWith('image/') ? (
                              <div className="relative inline-block">
                                <img src={_proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex'; }} />
                                <div className="hidden flex-col items-center justify-center p-8 bg-slate-100 rounded-md text-slate-500 border border-slate-200">
                                  <span className="text-2xl mb-2">??</span>
                                  <span className="text-xs text-center">Media Expired<br/>or Unavailable</span>
                                </div>
                                <a href={_proxySrc} target="_blank" rel="noopener noreferrer" download className="absolute top-2 right-2 bg-black/50 text-white p-1.5 rounded-full opacity-0 group-hover/media:opacity-100 transition-opacity" title="Download / View Fullscreen">
                                  <Paperclip className="w-4 h-4" />
                                </a>
                              </div>
                            ) : _mime.startsWith('video/') ? (
                              <div className="relative inline-block">
                                <video src={_proxySrc} controls className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                                <a href={_proxySrc} target="_blank" rel="noopener noreferrer" download className="absolute top-2 right-2 bg-black/50 text-white p-1.5 rounded-full opacity-0 group-hover/media:opacity-100 transition-opacity" title="Download / View Fullscreen">
                                  <Paperclip className="w-4 h-4" />
                                </a>
                              </div>
                            ) : _mime.startsWith('audio/') ? (
                              <audio src={_proxySrc} controls className="max-w-full" />
                            ) : (
                              <a href={_proxySrc} target="_blank" rel="noopener noreferrer" download className="text-blue-600 hover:underline flex items-center gap-1 text-sm bg-slate-100 p-2 rounded">
                                <Paperclip className="w-4 h-4" /> Download / View File
                              </a>
                            )}
                          </div>
                        )}
                        {msg.full_body || msg.body_preview ? (
                          <p className="text-sm whitespace-pre-wrap break-words">{msg.full_body || msg.body_preview}</p>
                        ) : msg.has_media ? null : (
                          <p className="text-sm whitespace-pre-wrap break-words italic text-slate-500">(Unsupported Message Type)</p>
                        )}
                        <div className="flex items-center justify-end gap-1 mt-1">
                          <span className="text-[10px] text-slate-500">{formatTime(msg.created_at)}</span>
                          {isMe && (
                            <span className="text-[10px] text-slate-500 ml-1">
                              {msg.status === 'READ' ? '✓✓' : msg.status === 'DELIVERED' ? '✓✓' : '✓'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
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
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-slate-500">
            <div className="w-64 h-64 mb-6 opacity-30 rounded-full border-4 border-dashed border-slate-400 flex items-center justify-center bg-slate-100">
               <Phone className="w-24 h-24 text-slate-500" />
            </div>
            <h2 className="text-2xl font-light text-slate-700 mb-2">WhatsApp Web</h2>
            <p className="text-sm max-w-md">Select a conversation to start messaging. Messages are end-to-end encrypted.</p>
          </div>
        )}
      </div>
      {/* Contact Profile Panel */}
      {selectedChat && showProfilePanel && (
        <div className="w-80 border-l border-slate-200 bg-white flex flex-col flex-shrink-0 animate-in slide-in-from-right overflow-y-auto">
          <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
            <h2 className="font-semibold text-slate-800">{selectedChat.contact_name || formatPhoneFromChatId(selectedChat.chat_id) || selectedChat.prospect_phone || "Unknown Contact"}</h2>
            <button onClick={() => setShowProfilePanel(false)} className="text-slate-400 hover:text-slate-600 text-xl font-bold">&times;</button>
          </div>
          
          <div className="p-6 flex flex-col items-center border-b border-slate-100">
            <div className="w-32 h-32 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-4xl mb-4 overflow-hidden relative shadow-sm">
              <img src={API_BASE + "/whatsapp/profile-pic/" + (wahaContact && wahaContact.id ? wahaContact.id : selectedChat.chat_id) + "/"} className="w-full h-full object-cover relative z-10" onError={(e) => e.target.style.display = 'none'} />
              <span className="absolute inset-0 flex items-center justify-center">{selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : '#'}</span>
            </div>
            <h3 className="text-xl font-bold text-slate-800 text-center">{(wahaContact && wahaContact.pushname) ? wahaContact.pushname : (selectedChat.contact_name || "Unknown Contact")}</h3>
            <p className="text-slate-500 text-sm mt-1 font-mono">{formatPhoneFromChatId(selectedChat.chat_id) || (wahaContact && wahaContact.phoneNumber ? formatPhoneFromChatId(wahaContact.phoneNumber) : '') || selectedChat.prospect_phone || 'Loading...'}</p>
          </div>

          <div className="p-4 space-y-4">
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Company</label>
              <p className="text-slate-800 mt-1">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Not linked to CRM'}</p>
            </div>
            
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chat ID</label>
              <p className="text-slate-800 mt-1 text-sm break-all">{selectedChat.chat_id}</p>
            </div>
            
            <div>
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

