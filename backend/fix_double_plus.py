with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# We want to replace:
# "+" + formatPhoneFromChatId
# With just:
# formatPhoneFromChatId

content = content.replace('"+" + formatPhoneFromChatId', 'formatPhoneFromChatId')

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed double plus sign')
