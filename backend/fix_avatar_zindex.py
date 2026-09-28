with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Fix absolute z-[-1] on all avatars
content = re.sub(r'className="absolute z-\[-1\]"', 'className="absolute z-0"', content)

# But wait, if the img has no z-index, they are both in flow if relative/absolute. 
# Let's just make the image z-10 and absolute, or make the img relative z-10.
# Actually, if img is display='none', it just disappears! So the span can just be static or absolute z-0.
# Let's make the span just absolute inset-0 flex items-center justify-center.

old_span = '<span className="absolute z-[-1]">'
new_span = '<span className="absolute inset-0 flex items-center justify-center">'
content = content.replace(old_span, new_span)

old_img_class = 'className="w-full h-full object-cover"'
new_img_class = 'className="w-full h-full object-cover relative z-10"'
content = content.replace(old_img_class, new_img_class)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed avatar fallback visibility')
