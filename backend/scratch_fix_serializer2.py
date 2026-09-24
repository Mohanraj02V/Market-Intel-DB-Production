import sys

path = r'c:\Users\mohan\OneDrive\Desktop\market-intel\Market-Intel-DB\backend\prospects\serializers.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target_callback = """    def get_key_person_name(self, obj):
        first_contact = obj.prospect.key_contacts.first()
        if first_contact:
            return first_contact.contact_name
        return None"""

rep_callback = """    def get_key_person_name(self, obj):
        if hasattr(obj, 'prospect_contact') and obj.prospect_contact:
            return obj.prospect_contact.contact_name
        first_contact = obj.prospect.key_contacts.first()
        if first_contact:
            return first_contact.contact_name
        return None"""

text = text.replace(target_callback, rep_callback)
target_callback_cr = target_callback.replace('\n', '\r\n')
rep_callback_cr = rep_callback.replace('\n', '\r\n')
text = text.replace(target_callback_cr, rep_callback_cr)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Done")
