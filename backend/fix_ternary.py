with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = re.sub(
    r'\{formatPhoneFromChatId\(selectedChat\.chat_id\)\s*\?\s*.*?:\s*\'Phone hidden\'\}',
    r"{formatPhoneFromChatId(selectedChat.chat_id) ? '+' + formatPhoneFromChatId(selectedChat.chat_id) : 'Phone hidden'}",
    content
)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
