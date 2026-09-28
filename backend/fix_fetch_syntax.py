with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Fix the broken fetch call
broken_fetch = r'fetch\(http://localhost:8000/api/whatsapp/contact-info/\\/\)'
fixed_fetch = r'fetch("http://localhost:8000/api/whatsapp/contact-info/" + selectedChat.chat_id + "/")'
content = re.sub(broken_fetch, fixed_fetch, content)

# Check if there's any other broken fetch just in case
broken_fetch2 = r'fetch\(http://localhost:8000/api/whatsapp/contact-info//\)'
content = re.sub(broken_fetch2, fixed_fetch, content)

# Let's just catch anything that looks like fetch(http:...)
content = re.sub(r'fetch\(http://localhost:8000/api/whatsapp/contact-info/.*?\)', fixed_fetch, content)


with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed fetch syntax')
