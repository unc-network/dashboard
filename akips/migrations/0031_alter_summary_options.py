# Generated by Django 3.2.15 on 2022-09-21 14:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0030_alter_summary_tier'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='summary',
            options={'ordering': ['tier', '-type', 'name', 'first_event']},
        ),
    ]