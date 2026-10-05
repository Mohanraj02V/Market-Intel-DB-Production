from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('prospects', '0025_leadqualification_assigned_lq'),
    ]

    operations = [
        migrations.AddField(
            model_name='prospect',
            name='ownership_sector',
            field=models.CharField(choices=[('Private Company', 'Private Company'), ('Government Company', 'Government Company'), ('Semi Government Company', 'Semi Government Company')], default='Private Company', max_length=50),
        ),
    ]
