with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_response = '''        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                return Response(data)
        except Exception as e:
            return Response({"detail": str(e)}, status=404)'''

new_response = '''        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return Response({"detail": str(e)}, status=404)

        # Enrich with CRM company info from LQ pipeline
        phone_number = data.get("phoneNumber", "")
        if phone_number:
            import re as _re
            phone_digits = _re.sub(r"\\D+", "", phone_number)[-10:]  # last 10 digits
            try:
                from prospects.models import ProspectContact
                for contact in ProspectContact.objects.select_related("prospect").filter(
                    phone_number__isnull=False
                ):
                    stored_digits = _re.sub(r"\\D+", "", contact.phone_number or "")[-10:]
                    if stored_digits == phone_digits:
                        if contact.prospect:
                            data["company"] = contact.prospect.company_name
                            data["contact_name"] = contact.contact_name
                        break
            except Exception:
                pass

        return Response(data)'''

content = content.replace(old_response, new_response)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated WhatsAppContactInfoView with CRM lookup')
