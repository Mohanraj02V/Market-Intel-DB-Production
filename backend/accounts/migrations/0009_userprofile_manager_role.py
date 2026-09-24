from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_remove_mailaccount_company_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('PRE', 'Prospect Research Engineer'),
                    ('LQ', 'Lead Qualifier'),
                    ('MANAGER', 'Manager'),
                ],
                default='PRE',
                max_length=10,
            ),
        ),
    ]
