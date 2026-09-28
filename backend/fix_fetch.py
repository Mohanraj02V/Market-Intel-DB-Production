with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_use_effect = '''  useEffect(() => {
    if (showProfilePanel && selectedChat) {
      setWahaContact(null);
      fetch("http://localhost:8000/api/whatsapp/contact-info/" + selectedChat.chat_id + "/")
        .then(r => r.json())
        .then(data => {
            if (data.phoneNumber) {
                setWahaContact(data);
            }
        }).catch(err => console.error(err));
    }
  }, [showProfilePanel, selectedChat]);'''

new_use_effect = '''  useEffect(() => {
    if (selectedChat) {
      setWahaContact(null);
      fetch("http://localhost:8000/api/whatsapp/contact-info/" + selectedChat.chat_id + "/")
        .then(r => r.json())
        .then(data => {
            if (data.phoneNumber) {
                setWahaContact(data);
            }
        }).catch(err => console.error(err));
    }
  }, [selectedChat]);'''

content = content.replace(old_use_effect, new_use_effect)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated useEffect to run on chat selection')
