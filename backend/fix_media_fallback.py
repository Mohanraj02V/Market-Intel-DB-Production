with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the img tag onError to show a fallback instead of hiding
old_img = '''<img src={_proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; }} />'''

new_img = '''<img src={_proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex'; }} />
                                <div className="hidden flex-col items-center justify-center p-8 bg-slate-100 rounded-md text-slate-500 border border-slate-200">
                                  <span className="text-2xl mb-2">??</span>
                                  <span className="text-xs text-center">Media Expired<br/>or Unavailable</span>
                                </div>'''

content = content.replace(old_img, new_img)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed media fallback')
