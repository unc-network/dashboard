from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0084_delete_tdxincident'),
    ]

    operations = [
        migrations.CreateModel(
            name='TDXConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('api_url', models.URLField(blank=True, default='')),
                ('flow_url', models.URLField(blank=True, default='')),
                ('username', models.CharField(blank=True, default='', max_length=255)),
                ('password', models.CharField(blank=True, default='', max_length=255)),
                ('apikey', models.CharField(blank=True, default='', max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'TDX configuration',
                'verbose_name_plural': 'TDX configuration',
            },
        ),
    ]
