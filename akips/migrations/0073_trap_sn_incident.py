# Generated by Django 3.2.15 on 2023-03-20 12:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0072_auto_20230320_0847'),
    ]

    operations = [
        migrations.AddField(
            model_name='trap',
            name='sn_incident',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='akips.servicenowincident'),
        ),
    ]