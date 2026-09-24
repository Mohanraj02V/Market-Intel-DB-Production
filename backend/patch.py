import os

with open('prospects/views.py', 'r') as f:
    content = f.read()

target = '        from .serializers import AuditReverificationRequestSerializer'
replacement = '''        try:
            lq = prospect.lead_qualification
            lq.pre_task_status = LeadQualification.PreTaskStatus.ISSUE_SENT_TO_PRE
            lq.issue_category = 'Audit: Re-Verification Required'
            lq.issue_details = f"Manager Notes: {manager_notes}\\nFields: {', '.join(highlighted_fields)}"
            lq.issue_reported_by = request.user
            lq.issue_reported_at = timezone.now()
            for field in highlighted_fields:
                lq.verification_checklist[field] = 'Incorrect'
            lq.save()
        except Exception as e:
            print("Failed to update LeadQualification on audit_reverify:", e)
            
''' + target

with open('prospects/views.py', 'w') as f:
    f.write(content.replace(target, replacement))
print("Done")
