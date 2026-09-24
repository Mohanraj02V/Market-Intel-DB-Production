import sys

path = r'c:\Users\mohan\OneDrive\Desktop\market-intel\Market-Intel-DB\backend\prospects\serializers.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = """class CallbackReminderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='prospect.company_name', read_only=True)

    class Meta:
        model = CallbackReminder
        fields = [
            'id', 'prospect', 'company_name', 'scheduled_datetime',
            'description', 'is_completed', 'notified_30m',
            'notified_15m', 'notified_5m', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']"""

replacement = """class CallbackReminderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='prospect.company_name', read_only=True)
    key_person_name = serializers.SerializerMethodField()

    class Meta:
        model = CallbackReminder
        fields = [
            'id', 'prospect', 'company_name', 'key_person_name', 'scheduled_datetime',
            'description', 'is_completed', 'notified_30m',
            'notified_15m', 'notified_5m', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_key_person_name(self, obj):
        first_contact = obj.prospect.key_contacts.first()
        if first_contact:
            return first_contact.contact_name
        return None"""

text = text.replace(target, replacement)
target_cr = target.replace('\n', '\r\n')
replacement_cr = replacement.replace('\n', '\r\n')
text = text.replace(target_cr, replacement_cr)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Done")
