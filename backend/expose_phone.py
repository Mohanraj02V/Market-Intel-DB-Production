with open('whatsapp/serializers.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add prospect_phone field
old_fields = '''            "prospect_name",
            "prospect_contact",'''
new_fields = '''            "prospect_name",
            "prospect_phone",
            "prospect_contact",'''
content = content.replace(old_fields, new_fields)

old_field_def = '''    prospect_name = serializers.SerializerMethodField()'''
new_field_def = '''    prospect_name = serializers.SerializerMethodField()
    prospect_phone = serializers.SerializerMethodField()'''
content = content.replace(old_field_def, new_field_def)

old_prospect_name_method = '''    def get_prospect_name(self, obj):
        if obj.prospect:
            return obj.prospect.company_name
        return None'''
new_prospect_name_method = '''    def get_prospect_name(self, obj):
        if obj.prospect:
            return obj.prospect.company_name
        return None
        
    def get_prospect_phone(self, obj):
        if obj.prospect_contact and getattr(obj.prospect_contact, 'phone', None):
            return obj.prospect_contact.phone
        return None'''
content = content.replace(old_prospect_name_method, new_prospect_name_method)

with open('whatsapp/serializers.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Exposed prospect_phone')
