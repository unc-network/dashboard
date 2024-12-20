# Generated by Django 4.2.16 on 2024-10-31 12:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0080_device_notify'),
    ]

    operations = [
        migrations.CreateModel(
            name='TDXIncident',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=10)),
                ('active', models.BooleanField(default=True)),
            ],
        ),
        migrations.AddField(
            model_name='summary',
            name='tdx_incident',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='akips.tdxincident'),
        ),
        migrations.AddField(
            model_name='trap',
            name='tdx_incident',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='akips.tdxincident'),
        ),
    ]
