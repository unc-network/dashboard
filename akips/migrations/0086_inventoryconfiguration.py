from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0085_tdxconfiguration'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('inventory_url', models.URLField(blank=True, default='')),
                ('inventory_token', models.CharField(blank=True, default='', max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Inventory configuration',
                'verbose_name_plural': 'Inventory configuration',
            },
        ),
    ]
