# Generated by Django 3.2.15 on 2022-09-07 19:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0010_auto_20220907_1451'),
    ]

    operations = [
        migrations.AlterField(
            model_name='group',
            name='device',
            field=models.ManyToManyField(to='akips.Device'),
        ),
    ]