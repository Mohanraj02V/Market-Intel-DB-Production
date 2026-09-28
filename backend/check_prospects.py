import os, sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.stdout.reconfigure(encoding='utf-8')
django.setup()

from prospects.models import Prospect, LeadQualification, assign_lq_to_prospect
from django.contrib.auth import get_user_model

User = get_user_model()
lq_users = list(User.objects.filter(profile__role='LQ', is_superuser=False).order_by('id'))
N = len(lq_users)

print(f"Found {N} LQ users: {[u.username for u in lq_users]}")
print()

# Fix ALL prospects that have NULL assigned_lq
prospects = list(Prospect.objects.all().order_by('created_at'))
fixed = 0
for idx, p in enumerate(prospects):
    try:
        lq = p.lead_qualification
        if lq.assigned_lq is None:
            # Assign based on creation order position
            expected_index = (idx // 5) % N
            lq.assigned_lq = lq_users[expected_index]
            lq.save(update_fields=['assigned_lq'])
            print(f"Fixed: {p.company_name} (pos={idx}) -> {lq_users[expected_index].username}")
            fixed += 1
    except Exception as e:
        print(f"Error for {p.company_name}: {e}")

print(f"\nTotal fixed: {fixed}")

print("\nFinal state:")
for u in lq_users:
    count = LeadQualification.objects.filter(assigned_lq=u).count()
    print(f"  {u.username}: {count} prospects")
null_count = LeadQualification.objects.filter(assigned_lq__isnull=True).count()
print(f"  NULL: {null_count}")
