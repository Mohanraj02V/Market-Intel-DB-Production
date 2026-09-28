with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

old_lookup = '''        # Enrich with CRM company info from LQ pipeline
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
                pass'''

new_lookup = '''        # Enrich with CRM company info from LQ pipeline
        phone_number = data.get("phoneNumber", "")
        if phone_number:
            import re as _re
            # Extract all digits from WAHA number
            waha_digits = _re.sub(r"\\D+", "", phone_number)
            # Typically WAHA returns country code + number. e.g., 919360239398
            # Let's get the core 10 digits assuming Indian/US length for fallback matching
            waha_core_10 = waha_digits[-10:] if len(waha_digits) >= 10 else waha_digits
            
            try:
                from prospects.models import ProspectContact
                for contact in ProspectContact.objects.select_related("prospect").filter(
                    phone_number__isnull=False
                ):
                    stored_digits = _re.sub(r"\\D+", "", contact.phone_number or "")
                    
                    # Fuzzy match: 
                    # 1. Exact match of all digits
                    # 2. Stored digits starts with WAHA core 10 (handles typo 936023939888)
                    # 3. WAHA core 10 matches stored core 10
                    stored_core_10 = stored_digits[-10:] if len(stored_digits) >= 10 else stored_digits
                    
                    if (stored_digits == waha_digits or 
                        (len(waha_core_10) == 10 and stored_digits.startswith(waha_core_10)) or
                        (len(waha_core_10) == 10 and stored_core_10 == waha_core_10) or
                        (len(waha_core_10) >= 8 and waha_core_10 in stored_digits)
                       ):
                        if contact.prospect:
                            data["company"] = contact.prospect.company_name
                            data["contact_name"] = contact.contact_name
                        break
            except Exception:
                pass'''

content = content.replace(old_lookup, new_lookup)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated WhatsAppContactInfoView with fuzzy CRM lookup')
