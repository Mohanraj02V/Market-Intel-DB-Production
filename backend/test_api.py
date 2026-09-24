import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from prospects.views import ProspectViewSet

User = get_user_model()
user = User.objects.first()

factory = APIRequestFactory()
request = factory.post('/api/prospects/033276a7-62eb-41e8-949d-e555ad87081a/audit-reverify/', {'highlighted_fields': ['parent_companies_detail'], 'manager_notes': 'test'}, format='json')

from rest_framework.test import force_authenticate
force_authenticate(request, user=user)

view = ProspectViewSet.as_view({'post': 'audit_reverify'})
try:
    response = view(request, pk='033276a7-62eb-41e8-949d-e555ad87081a')
    print('STATUS:', response.status_code)
    print('CONTENT:', response.data)
except Exception as e:
    import traceback
    traceback.print_exc()
