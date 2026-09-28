with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add wahaContact state
old_state = '''  const [showProfilePanel, setShowProfilePanel] = useState(false);'''
new_state = '''  const [showProfilePanel, setShowProfilePanel] = useState(false);
  const [wahaContact, setWahaContact] = useState(null);

  useEffect(() => {
    if (showProfilePanel && selectedChat) {
      setWahaContact(null);
      fetch(http://localhost:8000/api/whatsapp/contact-info/\/)
        .then(r => r.json())
        .then(data => {
            if (data.phoneNumber) {
                setWahaContact(data);
            }
        }).catch(err => console.error(err));
    }
  }, [showProfilePanel, selectedChat]);'''

content = content.replace(old_state, new_state)

# Use wahaContact.phoneNumber for the phone number
# I previously replaced it with:
# {formatPhoneFromChatId(selectedChat.chat_id) ? "+" + formatPhoneFromChatId(selectedChat.chat_id) : selectedChat.prospect_phone ? selectedChat.prospect_phone : "Phone hidden"}
# I'll find that and add wahaContact.phoneNumber check.

import re
content = re.sub(
    r'\{formatPhoneFromChatId\(selectedChat\.chat_id\).*?\}</p>',
    r'{formatPhoneFromChatId(selectedChat.chat_id) ? "+" + formatPhoneFromChatId(selectedChat.chat_id) : selectedChat.prospect_phone ? selectedChat.prospect_phone : (wahaContact?.phoneNumber ? "+" + formatPhoneFromChatId(wahaContact.phoneNumber) : "Phone hidden")}</p>',
    content
)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated UI to fetch and use WAHA contact info')
