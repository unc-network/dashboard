# Generated by Django 3.2.15 on 2022-10-27 11:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0060_auto_20221021_1106'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='hibernate',
            field=models.BooleanField(default=False),
        ),
    ]