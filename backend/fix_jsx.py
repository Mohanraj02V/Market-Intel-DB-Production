with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the broken IIFE media rendering with a clean helper-function approach
# The issue is the IIFE in JSX and the corrupted template literal

bad_block = '''                        {msg.has_media && (msg.media_url || msg.media_file) && (() => {
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

# The map already starts with: messages.map(msg => {  const isMe = ...
# We need to inject the const proxySrc BEFORE the return statement
# Replace the map callback to add the variable before return

old_map_start = '''                messages.map(msg => {
                  const isMe = msg.direction === 'OUTBOUND';
                  return ('''

new_map_start = '''                messages.map(msg => {
                  const isMe = msg.direction === 'OUTBOUND';
                  const _rawMediaSrc = msg.media_url || msg.media_file || '';
                  const _proxySrc = _rawMediaSrc ? ('http://localhost:8000/api/whatsapp/media-proxy/?url=' + encodeURIComponent(_rawMediaSrc)) : '';
                  const _mime = msg.media_mime_type || '';
                  return ('''

good_block = '''                        {msg.has_media && _proxySrc && (
                          <div className="mb-2">
                            {_mime.startsWith('image/') ? (
                              <img src={_proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; }} />
                            ) : _mime.startsWith('video/') ? (
                              <video src={_proxySrc} controls className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                            ) : _mime.startsWith('audio/') ? (
                              <audio src={_proxySrc} controls className="max-w-full" />
                            ) : (
                              <a href={_proxySrc} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-1 text-sm bg-slate-100 p-2 rounded">
                                <Paperclip className="w-4 h-4" /> Download / View File
                              </a>
                            )}
                          </div>
                        )}
                        {msg.full_body || msg.body_preview ? (
                          <p className="text-sm whitespace-pre-wrap break-words">{msg.full_body || msg.body_preview}</p>
                        ) : msg.has_media ? null : (
                          <p className="text-sm whitespace-pre-wrap break-words italic text-slate-500">(Unsupported Message Type)</p>
                        )}'''

content = content.replace(bad_block, good_block)
content = content.replace(old_map_start, new_map_start)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done! Checking if replacement worked...')
print('bad_block found:', bad_block in open('../frontend/src/pages/WhatsappPage.jsx', encoding='utf-8').read())
print('good_block found:', good_block in open('../frontend/src/pages/WhatsappPage.jsx', encoding='utf-8').read())
