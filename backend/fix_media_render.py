with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_media_render = '''                          <div className="mb-2">
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
                          </div>'''

new_media_render = '''                          <div className="mb-2 group/media relative">
                            {_mime.startsWith('image/') ? (
                              <div className="relative inline-block">
                                <img src={_proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; }} />
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
                          </div>'''

content = content.replace(old_media_render, new_media_render)
with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed media render UI:', new_media_render[:50] in content)
