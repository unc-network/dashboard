# Generated by Django 3.2.15 on 2022-09-09 13:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0014_device_maintenance'),
    ]

    operations = [
        migrations.AddField(
            model_name='summary',
            name='max_count',
            field=models.IntegerField(default=0),
        ),
    ]
