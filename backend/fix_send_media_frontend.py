with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_send = '''      await api.post('/whatsapp/send-media/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setAttachPreview(null);
      setMessage('');
      setToastMessage({ text: 'Media sent!', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);
      setTimeout(() => fetchMessages(selectedChat.id), 2000);'''

new_send = '''      const response = await api.post('/whatsapp/send-media/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setAttachPreview(null);
      setMessage('');
      
      // Append the new message instantly if the backend returns it
      if (response.data && response.data.id) {
        setMessages(prev => [...prev, response.data]);
        setTimeout(scrollToBottom, 100);
      } else {
        setTimeout(() => fetchMessages(selectedChat.id), 1000);
      }
      
      setToastMessage({ text: 'Media sent!', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);'''

content = content.replace(old_send, new_send)
with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed frontend send media:', new_send[:50] in content)
