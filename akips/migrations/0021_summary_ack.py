# Generated by Django 3.2.15 on 2022-09-15 12:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0020_auto_20220914_1551'),
    ]

    operations = [
        migrations.AddField(
            model_name='summary',
            name='ack',
            field=models.BooleanField(default=False),
        ),
    ]