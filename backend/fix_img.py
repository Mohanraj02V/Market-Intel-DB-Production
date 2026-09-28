with open('../frontend/src/pages/WhatsappPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

broken_img = '<img src={http://localhost:8000/api/whatsapp/profile-pic//} className="w-full h-full object-cover" onError={(e) => e.target.style.display = \'none\'} />'
fixed_img = '<img src={http://localhost:8000/api/whatsapp/profile-pic/ + selectedChat.chat_id + /} className="w-full h-full object-cover" onError={(e) => e.target.style.display = \'none\'} />'

# Let's just use string concat to avoid backtick issues in PowerShell string substitution altogether just in case.
fixed_img_safe = '<img src={"http://localhost:8000/api/whatsapp/profile-pic/" + selectedChat.chat_id + "/"} className="w-full h-full object-cover" onError={(e) => e.target.style.display = \'none\'} />'

content = content.replace(broken_img, fixed_img_safe)

broken_span = '<span className="absolute z-[-1]"></span>'
fixed_span = '<span className="absolute z-[-1]">{selectedChat.prospect_name ? selectedChat.prospect_name.charAt(0) : selectedChat.contact_name ? selectedChat.contact_name.charAt(0) : \'#\'}</span>'

content = content.replace(broken_span, fixed_span)

with open('../frontend/src/pages/WhatsappPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
