# Generated by Django 3.2.15 on 2022-09-23 13:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0037_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='snmptrap',
            name='comment',
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name='summary',
            name='comment',
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name='unreachable',
            name='comment',
            field=models.CharField(blank=True, max_length=1024),
        ),
    ]
