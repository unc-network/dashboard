# Generated by Django 3.2.15 on 2023-03-21 15:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0074_alter_servicenowincident_sys_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicenowincident',
            name='instance',
            field=models.CharField(default='uncchdev', max_length=32),
        ),
    ]
