with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_proxy = '''                  const _rawMediaSrc = msg.media_url || msg.media_file || '';
                  const _proxySrc = _rawMediaSrc.includes('localhost:3000') 
                    ? ('http://localhost:8000/api/whatsapp/media-proxy/?url=' + encodeURIComponent(_rawMediaSrc)) 
                    : _rawMediaSrc;'''

new_proxy = '''                  const _rawMediaSrc = msg.media_url || msg.media_file || '';
                  let _proxySrc = '';
                  if (_rawMediaSrc) {
                    if (_rawMediaSrc.includes('localhost:3000')) {
                      _proxySrc = 'http://localhost:8000/api/whatsapp/media-proxy/?url=' + encodeURIComponent(_rawMediaSrc);
                    } else if (_rawMediaSrc.startsWith('/')) {
                      _proxySrc = 'http://localhost:8000' + _rawMediaSrc;
                    } else {
                      _proxySrc = _rawMediaSrc;
                    }
                  }'''

content = content.replace(old_proxy, new_proxy)
with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed frontend URL logic:', new_proxy in content)
