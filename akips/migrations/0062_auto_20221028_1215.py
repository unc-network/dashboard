# Generated by Django 3.2.15 on 2022-10-28 16:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0061_device_hibernate'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='comment',
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name='hibernaterequest',
            name='executed',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
