# Generated by Django 3.2.15 on 2022-10-06 18:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0050_remove_device_akips_devic_ip4addr_0bbcf4_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='group',
            field=models.CharField(default='default', max_length=255),
        ),
    ]
