# Generated by Django 3.2.15 on 2022-10-06 13:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('akips', '0045_summary_moving_avg_count'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='status',
            name='akips_statu_object_b99fde_idx',
        ),
        migrations.RenameField(
            model_name='status',
            old_name='object',
            new_name='attribute',
        ),
        migrations.AddIndex(
            model_name='status',
            index=models.Index(fields=['attribute'], name='akips_statu_attribu_6e7396_idx'),
        ),
    ]
