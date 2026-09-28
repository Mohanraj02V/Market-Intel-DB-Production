with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the media rendering section to use the proxy URL
target = '''                        {msg.has_media && (msg.media_url || msg.media_file) && (
                          <div className="mb-2">
                            {(msg.media_mime_type || '').startsWith('image/') ? (
                              <img src={msg.media_url || msg.media_file} alt="Media message" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                            ) : (msg.media_mime_type || '').startsWith('video/') ? (
                              <video src={msg.media_url || msg.media_file} controls className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                            ) : (msg.media_mime_type || '').startsWith('audio/') ? (
                              <audio src={msg.media_url || msg.media_file} controls className="max-w-full" />
                            ) : (
                              <a href={msg.media_url || msg.media_file} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-1 text-sm bg-slate-100 p-2 rounded">
                                <Paperclip className="w-4 h-4" /> Download / View File
                              </a>
                            )}
                          </div>
                        )}
                        {msg.full_body || msg.body_preview ? (
                          <p className="text-sm whitespace-pre-wrap break-words">{msg.full_body || msg.body_preview}</p>
                        ) : msg.has_media ? (
                          <p className="text-xs text-slate-400 italic">Media message</p>
                        ) : (
                          <p className="text-sm whitespace-pre-wrap break-words italic text-slate-500">(Unsupported Message Type)</p>
                        )}'''

replacement = '''                        {msg.has_media && (msg.media_url || msg.media_file) && (() => {
                          const rawSrc = msg.media_url || msg.media_file;
                          const proxySrc = rawSrc ? http://localhost:8000/api/whatsapp/media-proxy/?url= : null;
                          const mime = msg.media_mime_type || '';
                          if (!proxySrc) return null;
                          return (
                            <div className="mb-2">
                              {mime.startsWith('image/') ? (
                                <img src={proxySrc} alt="Media message" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; }} />
                              ) : mime.startsWith('video/') ? (
                                <video src={proxySrc} controls className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                              ) : mime.startsWith('audio/') ? (
                                <audio src={proxySrc} controls className="max-w-full" />
                              ) : (
                                <a href={proxySrc} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-1 text-sm bg-slate-100 p-2 rounded">
                                  <Paperclip className="w-4 h-4" /> Download / View File
                                </a>
                              )}
                            </div>
                          );
                        })()}
                        {msg.full_body || msg.body_preview ? (
                          <p className="text-sm whitespace-pre-wrap break-words">{msg.full_body || msg.body_preview}</p>
                        ) : msg.has_media ? null : (
                          <p className="text-sm whitespace-pre-wrap break-words italic text-slate-500">(Unsupported Message Type)</p>
                        )}'''

content = content.replace(target, replacement)
with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
