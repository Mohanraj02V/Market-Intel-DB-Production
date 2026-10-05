from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('market_events', '0005_remove_marketevent_company_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='marketevent',
            name='website_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
