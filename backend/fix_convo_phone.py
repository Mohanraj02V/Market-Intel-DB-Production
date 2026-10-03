with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = '''        if session_id:
            session_obj = WhatsAppSession.objects.filter(id=session_id).first()
            if session_obj and session_obj.phone_number:
                # If they select a specific session and it has a phone number,
                # show ALL conversations across any session with this phone number.
                # We don't filter by assigned_profiles here because old sessions might be unassigned.
                qs = WhatsAppConversation.objects.select_related(
                    "prospect_contact", "prospect", "session"
                ).filter(
                    session__phone_number=session_obj.phone_number,
                    is_deleted=False,
                )
            else:
                qs = qs.filter(session_id=session_id)'''

new_logic = '''        if session_id:
            session_obj = WhatsAppSession.objects.filter(id=session_id).first()
            if session_obj:
                # If phone_number is missing, try to fetch it dynamically from WAHA
                if not session_obj.phone_number:
                    import urllib.request
                    import json
                    import os
                    waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
                    api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
                    req = urllib.request.Request(f"{waha_url}/api/sessions/")
                    if api_key:
                        req.add_header("X-Api-Key", api_key)
                    try:
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            waha_sessions = json.loads(resp.read().decode("utf-8"))
                            for ws in waha_sessions:
                                if ws.get("name") == session_obj.session_name:
                                    me_info = ws.get("me")
                                    if me_info and me_info.get("id"):
                                        session_obj.phone_number = me_info.get("id").split("@")[0]
                                        session_obj.save(update_fields=["phone_number"])
                                    break
                    except Exception as e:
                        print("Failed to dynamically fetch session phone_number:", e)
                
                if session_obj.phone_number:
                    # Show ALL conversations across any session with this phone number.
                    qs = WhatsAppConversation.objects.select_related(
                        "prospect_contact", "prospect", "session"
                    ).filter(
                        session__phone_number=session_obj.phone_number,
                        is_deleted=False,
                    )
                else:
                    qs = qs.filter(session_id=session_id)'''

content = content.replace(old_logic, new_logic)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated WhatsAppConversationsView to dynamically sync phone number')
