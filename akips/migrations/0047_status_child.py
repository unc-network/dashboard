# Generated by Django 3.2.15 on 2022-10-06 13:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0046_auto_20221006_0904'),
    ]

    operations = [
        migrations.AddField(
            model_name='status',
            name='child',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
    ]