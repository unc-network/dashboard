# Generated by Django 3.2.15 on 2022-10-01 15:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0039_status_statusalert'),
    ]

    operations = [
        migrations.AddField(
            model_name='summary',
            name='ups_battery',
            field=models.IntegerField(default=0),
        ),
    ]
