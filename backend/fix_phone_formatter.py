with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us')) {
      return '+' + chatId.split('@')[0];
    }
    return '';
  };'''

new_func = '''const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us') || chatId.includes('@s.whatsapp.net')) {
      return '+' + chatId.split('@')[0];
    }
    return '';
  };'''

content = content.replace(old_func, new_func)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed phone formatter')
