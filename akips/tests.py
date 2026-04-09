import json
import os
import tempfile
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_celery_results.models import TaskResult
from unittest.mock import patch

from .models import TDXConfiguration, InventoryConfiguration, AKIPSConfiguration, APIAccessKey, Summary, Device, Status, Unreachable, create_profile, save_profile
from .ocnes import EventManager
from .task import (
    SNAPSHOT_FIXTURE_LABELS,
    get_snapshot_import_models,
    import_snapshot_task,
    materialize_snapshot_import_source,
    refresh_inventory,
    refresh_akips_devices,
    refresh_unreachable,
    sanitize_snapshot_for_import,
)
from .session_tracking import SESSION_LOGIN_AT_KEY
from .views import Home, Users


class PwaViewTests(SimpleTestCase):
    def test_manifest_is_available(self):
        response = self.client.get(reverse('pwa_manifest'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/manifest+json'))
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['name'], 'OCNES Dashboard')
        self.assertEqual(payload['start_url'], reverse('home'))
        self.assertEqual(payload['display'], 'standalone')
        self.assertEqual(payload['theme_color'], '#007fae')
        self.assertEqual(payload['icons'][0]['sizes'], '192x192')

    def test_service_worker_is_available(self):
        response = self.client.get(reverse('service_worker'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/javascript'))
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertContains(response, 'const CACHE_NAME =')
        self.assertContains(response, reverse('pwa_offline'))
        self.assertContains(response, reverse('home'))
        self.assertContains(response, reverse('about'))
        self.assertContains(response, "pathname.indexOf('/api/') === 0")

    def test_offline_page_is_available(self):
        response = self.client.get(reverse('pwa_offline'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Connection Required')
        self.assertContains(response, 'live OCNES data is not available offline yet')


class HomeHudScaleTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = Home.as_view()
        self.user = User(username='hudtester')

    def test_hud_route_uses_default_scale(self):
        request = self.factory.get('/hud/')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request, hud_mode=True)
            context = mock_render.call_args.kwargs['context']

        self.assertTrue(context['hud_mode'])
        self.assertEqual(context['hud_font_scale'], 1.0)

    def test_hud_route_accepts_valid_scale(self):
        request = self.factory.get('/hud/?scale=1.5')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request, hud_mode=True)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(context['hud_font_scale'], 1.5)

    def test_hud_route_uses_default_for_invalid_scale(self):
        request = self.factory.get('/hud/?scale=abc')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request, hud_mode=True)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(context['hud_font_scale'], 1.0)

    def test_hud_route_clamps_low_scale(self):
        request = self.factory.get('/hud/?scale=0.2')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request, hud_mode=True)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(context['hud_font_scale'], 1.0)

    def test_hud_route_clamps_high_scale(self):
        request = self.factory.get('/hud/?scale=9')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request, hud_mode=True)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(context['hud_font_scale'], 1.9)

    def test_non_hud_route_keeps_hud_scale_neutral(self):
        request = self.factory.get('/')
        request.user = self.user
        with patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request)
            context = mock_render.call_args.kwargs['context']

        self.assertFalse(context['hud_mode'])
        self.assertEqual(context['hud_font_scale'], 1.0)

    def test_requires_login_redirects_anonymous(self):
        request = self.factory.get('/hud/?scale=1.5')
        request.user = AnonymousUser()
        response = self.view(request, hud_mode=True)

        self.assertEqual(response.status_code, 302)


class SettingsViewTests(TestCase):
    def setUp(self):
        self.url = reverse('settings')
        self.user = User.objects.create_user(username='viewer', password='testpass123')
        self.staff_user = User.objects.create_user(
            username='staff_admin',
            password='testpass123',
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username='super_admin',
            email='super_admin@example.com',
            password='testpass123',
        )

    def test_anonymous_user_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def _create_task_result(self, **kwargs):
        date_created = kwargs.pop('date_created', None)
        date_done = kwargs.pop('date_done', None)
        task_result = TaskResult.objects.create(**kwargs)

        update_fields = {}
        if date_created is not None:
            update_fields['date_created'] = date_created
        if date_done is not None:
            update_fields['date_done'] = date_done

        if update_fields:
            TaskResult.objects.filter(pk=task_result.pk).update(**update_fields)
            task_result.refresh_from_db()

        return task_result

    def test_non_superuser_is_forbidden(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_access_settings_page(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Settings')

    def test_superuser_can_access_settings_page(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_settings_page_shows_empty_import_status(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Last Import Status')
        self.assertContains(response, 'No snapshot import has run yet.')

    @patch('akips.views.call_command')
    def test_staff_can_export_snapshot(self, mock_call_command):
        self.client.force_login(self.staff_user)
        response = self.client.post(self.url, {'action': 'export_snapshot'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment; filename="ocnes-snapshot-', response['Content-Disposition'])
        self.assertEqual(mock_call_command.call_count, 1)
        self.assertEqual(mock_call_command.call_args[0][0], 'dumpdata')
        self.assertEqual(mock_call_command.call_args[0][1:], SNAPSHOT_FIXTURE_LABELS)
        self.assertIn('akips.apiaccesskey', mock_call_command.call_args.kwargs['exclude'])

    @patch('akips.views.import_snapshot_task.delay')
    @patch('akips.views.Settings._cache_uploaded_snapshot')
    def test_staff_can_import_snapshot(self, mock_cache_uploaded_snapshot, mock_import_delay):
        self.client.force_login(self.staff_user)
        mock_cache_uploaded_snapshot.return_value = 'snapshot-import-cache-key'
        upload = SimpleUploadedFile('snapshot.json', b'[]', content_type='application/json')

        response = self.client.post(
            self.url,
            {'action': 'import_snapshot', 'snapshot_file': upload},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_cache_uploaded_snapshot.call_count, 1)
        self.assertEqual(mock_import_delay.call_count, 1)
        self.assertEqual(mock_import_delay.call_args.args, ('snapshot-import-cache-key',))
        self.assertEqual(mock_import_delay.call_args.kwargs, {'clear_existing_data': False})

    @patch('akips.views.import_snapshot_task.delay')
    @patch('akips.views.Settings._cache_uploaded_snapshot')
    def test_import_can_clear_existing_data(self, mock_cache_uploaded_snapshot, mock_import_delay):
        self.client.force_login(self.staff_user)
        mock_cache_uploaded_snapshot.return_value = 'snapshot-import-cache-key'
        upload = SimpleUploadedFile('snapshot.json', b'[]', content_type='application/json')

        response = self.client.post(
            self.url,
            {
                'action': 'import_snapshot',
                'clear_existing_data': 'on',
                'snapshot_file': upload,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_cache_uploaded_snapshot.call_count, 1)
        self.assertEqual(mock_import_delay.call_count, 1)
        self.assertEqual(mock_import_delay.call_args.args, ('snapshot-import-cache-key',))
        self.assertEqual(mock_import_delay.call_args.kwargs, {'clear_existing_data': True})

    def test_import_rejects_non_json_file(self):
        self.client.force_login(self.staff_user)
        upload = SimpleUploadedFile('snapshot.txt', b'invalid', content_type='text/plain')

        response = self.client.post(
            self.url,
            {'action': 'import_snapshot', 'snapshot_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Snapshot file must end with .json or .json.gz')

    @override_settings(SNAPSHOT_IMPORT_MAX_BYTES=3)
    def test_import_rejects_oversized_snapshot_file(self):
        self.client.force_login(self.staff_user)
        upload = SimpleUploadedFile('snapshot.json', b'1234', content_type='application/json')

        response = self.client.post(
            self.url,
            {'action': 'import_snapshot', 'snapshot_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Snapshot file exceeds the maximum allowed size')

    @override_settings(SNAPSHOT_IMPORT_MAX_BYTES=3)
    def test_import_form_displays_snapshot_size_limit(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Maximum size: 3 bytes')

    def test_settings_page_shows_tdx_card(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TDX Integration')
        self.assertContains(response, 'Save TDX Settings')

    def test_settings_page_shows_akips_card_first(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        content = response.content.decode('utf-8')
        self.assertLess(content.find('AKIPS Integration'), content.find('TDX Integration'))

    def test_staff_can_save_tdx_settings(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.url,
            {
                'action': 'save_tdx_settings',
                'tdx-enabled': 'on',
                'tdx-api_url': 'https://tdx.example.edu/TDWebApi/',
                'tdx-flow_url': 'https://flows.example.edu/create/',
                'tdx-username': 'tdx-user',
                'tdx-password': 'tdx-pass',
                'tdx-apikey': 'tdx-key',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)

        config = TDXConfiguration.get_solo()
        self.assertTrue(config.enabled)
        self.assertEqual(config.api_url, 'https://tdx.example.edu/TDWebApi/')
        self.assertEqual(config.flow_url, 'https://flows.example.edu/create/')
        self.assertEqual(config.username, 'tdx-user')
        self.assertEqual(config.password, 'tdx-pass')
        self.assertEqual(config.apikey, 'tdx-key')

    def test_settings_page_shows_inventory_card(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'External Inventory Feed')
        self.assertContains(response, 'Save Inventory Settings')

    def test_staff_can_save_inventory_settings(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.url,
            {
                'action': 'save_inventory_settings',
                'inventory-enabled': 'on',
                'inventory-inventory_url': 'https://inventory.example.edu/full_dump.json',
                'inventory-inventory_token': 'inventory-secret-token',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)

        config = InventoryConfiguration.get_solo()
        self.assertTrue(config.enabled)
        self.assertEqual(config.inventory_url, 'https://inventory.example.edu/full_dump.json')
        self.assertEqual(config.inventory_token, 'inventory-secret-token')

    def test_settings_page_shows_api_key_card(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API Access Keys')
        self.assertContains(response, 'Create API Key')

    def test_settings_page_defaults_api_key_scopes_to_all_endpoints(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        form = response.context['api_key_form']
        self.assertCountEqual(
            form['allowed_endpoints'].value(),
            [choice[0] for choice in APIAccessKey.endpoint_choices()],
        )

    def test_staff_can_create_api_key(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.url,
            {
                'action': 'create_api_key',
                'name': 'Reporting integration',
                'allowed_endpoints': [APIAccessKey.Endpoint.SUMMARIES_READ],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Store this key now')
        access_key = APIAccessKey.objects.get(name='Reporting integration')
        self.assertEqual(access_key.created_by, self.staff_user)
        self.assertEqual(access_key.allowed_endpoints, [APIAccessKey.Endpoint.SUMMARIES_READ])
        self.assertTrue(access_key.is_active)
        self.assertNotEqual(access_key.hashed_key, '')
        self.assertNotEqual(access_key.hashed_key, access_key.key_prefix)
        self.assertContains(response, access_key.key_prefix)

    def test_staff_can_revoke_api_key(self):
        self.client.force_login(self.staff_user)
        access_key, _raw_key = APIAccessKey.create_with_generated_key(
            name='Legacy reporting integration',
            allowed_endpoints=[APIAccessKey.Endpoint.SUMMARIES_READ],
            created_by=self.staff_user,
        )

        response = self.client.post(
            self.url,
            {
                'action': 'revoke_api_key',
                'api_key_id': access_key.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        access_key.refresh_from_db()
        self.assertFalse(access_key.is_active)

    @patch('akips.views.refresh_inventory.delay')
    def test_staff_can_queue_inventory_sync(self, mock_delay):
        config = InventoryConfiguration.get_solo()
        config.enabled = True
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_inventory_sync'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_delay.call_count, 1)

    @patch('akips.views.refresh_inventory.delay')
    def test_inventory_sync_not_queued_when_disabled(self, mock_delay):
        config = InventoryConfiguration.get_solo()
        config.enabled = False
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_inventory_sync'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_delay.call_count, 0)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn('Inventory sync was not started because the external inventory feed is disabled.', messages)

    @patch('akips.views.refresh_akips_devices.delay')
    def test_staff_can_queue_akips_device_sync(self, mock_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = True
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_refresh_akips_devices'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_delay.call_count, 1)

    @patch('akips.views.refresh_akips_devices.delay')
    def test_stale_akips_device_sync_record_does_not_block_queue(self, mock_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = True
        config.save()
        self.client.force_login(self.staff_user)
        stale_started = timezone.now() - timezone.timedelta(hours=2)
        self._create_task_result(
            task_id='stale-akips-sync',
            task_name='akips.task.refresh_akips_devices',
            status='STARTED',
            date_created=stale_started,
            date_done=stale_started,
        )

        response = self.client.post(self.url, {'action': 'run_refresh_akips_devices'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_delay.call_count, 1)

    @patch('akips.views.refresh_akips_devices.delay')
    def test_recent_akips_device_sync_record_blocks_queue(self, mock_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = True
        config.save()
        self.client.force_login(self.staff_user)
        recent_started = timezone.now() - timezone.timedelta(minutes=5)
        self._create_task_result(
            task_id='recent-akips-sync',
            task_name='akips.task.refresh_akips_devices',
            status='STARTED',
            date_created=recent_started,
            date_done=recent_started,
        )

        response = self.client.post(self.url, {'action': 'run_refresh_akips_devices'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_delay.call_count, 0)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn('AKIPS device sync is already in progress.', messages)

    def test_about_page_ignores_stale_inflight_akips_sync(self):
        self.client.force_login(self.staff_user)
        completed_at = timezone.now() - timezone.timedelta(hours=1)
        self._create_task_result(
            task_id='completed-akips-sync',
            task_name='akips.task.refresh_akips_devices',
            status='SUCCESS',
            date_created=completed_at - timezone.timedelta(minutes=1),
            date_done=completed_at,
        )
        stale_started = timezone.now() - timezone.timedelta(hours=2)
        self._create_task_result(
            task_id='stale-inflight-akips-sync',
            task_name='akips.task.refresh_akips_devices',
            status='STARTED',
            date_created=stale_started,
            date_done=stale_started,
        )

        response = self.client.get(reverse('about'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SUCCESS')
        self.assertNotContains(response, 'In progress')

    @patch('akips.views.refresh_battery_test_status.delay')
    @patch('akips.views.refresh_ups_status.delay')
    @patch('akips.views.refresh_snmp_status.delay')
    @patch('akips.views.refresh_ping_status.delay')
    def test_staff_can_queue_combined_akips_status_sync(self, mock_ping_delay, mock_snmp_delay, mock_ups_delay, mock_battery_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = True
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_refresh_akips_status_sync'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_ping_delay.call_count, 1)
        self.assertEqual(mock_snmp_delay.call_count, 1)
        self.assertEqual(mock_ups_delay.call_count, 1)
        self.assertEqual(mock_battery_delay.call_count, 1)

    @patch('akips.views.refresh_battery_test_status.delay')
    @patch('akips.views.refresh_ups_status.delay')
    @patch('akips.views.refresh_snmp_status.delay')
    @patch('akips.views.refresh_ping_status.delay')
    def test_combined_akips_status_sync_not_queued_when_disabled(self, mock_ping_delay, mock_snmp_delay, mock_ups_delay, mock_battery_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = False
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_refresh_akips_status_sync'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_ping_delay.call_count, 0)
        self.assertEqual(mock_snmp_delay.call_count, 0)
        self.assertEqual(mock_ups_delay.call_count, 0)
        self.assertEqual(mock_battery_delay.call_count, 0)

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn('AKIPS status sync was not started because AKIPS integration is disabled.', messages)

    @patch('akips.views.refresh_akips_devices.delay')
    def test_akips_device_sync_not_queued_when_disabled(self, mock_delay):
        config = AKIPSConfiguration.get_solo()
        config.enabled = False
        config.save()
        self.client.force_login(self.staff_user)

        response = self.client.post(self.url, {'action': 'run_refresh_akips_devices'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_delay.call_count, 0)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn('AKIPS device sync was not started because AKIPS integration is disabled.', messages)

    @patch('akips.task.cache.delete')
    @patch('akips.task.call_command')
    @patch('akips.task.clear_snapshot_import_targets')
    @patch('akips.task.sanitize_snapshot_for_import', return_value='/tmp/mock-snapshot-sanitized.json')
    @patch('akips.task.materialize_snapshot_import_source', return_value=('/tmp/mock-snapshot.json', 'snapshot-import-cache-key'))
    @patch('akips.task.cache.add', return_value=True)
    @patch('akips.task.os.path.exists', return_value=False)
    def test_import_snapshot_task_uses_lock(self, mock_exists, mock_cache_add, mock_materialize, mock_sanitize_snapshot, mock_clear_targets, mock_call_command, mock_cache_delete):
        import_snapshot_task.run('snapshot-import-cache-key', clear_existing_data=True)

        self.assertEqual(mock_cache_add.call_count, 1)
        self.assertEqual(mock_cache_add.call_args.args, ('snapshot_import_task', True, 14400))
        self.assertEqual(mock_materialize.call_count, 1)
        self.assertEqual(mock_materialize.call_args.args, ('snapshot-import-cache-key',))
        self.assertEqual(mock_sanitize_snapshot.call_count, 1)
        self.assertEqual(mock_sanitize_snapshot.call_args.args, ('/tmp/mock-snapshot.json',))
        self.assertEqual(mock_sanitize_snapshot.call_args.kwargs, {'clear_existing_data': True})
        self.assertEqual(mock_clear_targets.call_count, 1)
        self.assertEqual(mock_call_command.call_count, 1)
        self.assertEqual(mock_call_command.call_args.args, ('loaddata', '/tmp/mock-snapshot-sanitized.json'))
        self.assertEqual(mock_cache_delete.call_count, 2)
        mock_cache_delete.assert_any_call('snapshot_import_task')
        mock_cache_delete.assert_any_call('snapshot-import-cache-key')

    @patch('akips.task.cache.get')
    def test_materialize_snapshot_import_source_reads_cached_payload(self, mock_cache_get):
        mock_cache_get.return_value = {
            'payload': b'[]',
            'suffix': '.json',
        }

        snapshot_path, cache_key = materialize_snapshot_import_source('snapshot-import-cache-key')
        self.addCleanup(lambda: os.path.exists(snapshot_path) and os.remove(snapshot_path))

        self.assertEqual(cache_key, 'snapshot-import-cache-key')
        self.assertTrue(os.path.exists(snapshot_path))
        with open(snapshot_path, 'rb') as snapshot_file:
            self.assertEqual(snapshot_file.read(), b'[]')

    @patch('akips.task.call_command')
    @patch('akips.task.cache.add', return_value=False)
    def test_import_snapshot_task_rejects_duplicate_run(self, mock_cache_add, mock_call_command):
        with self.assertRaises(RuntimeError):
            import_snapshot_task.run('/tmp/mock-snapshot.json', clear_existing_data=False)

        self.assertEqual(mock_cache_add.call_count, 1)
        self.assertEqual(mock_call_command.call_count, 0)

    @patch('akips.task.Inventory')
    @patch('akips.task.is_snapshot_import_in_progress', return_value=True)
    def test_refresh_inventory_skips_during_snapshot_import(self, mock_import_in_progress, mock_inventory):
        refresh_inventory.run()

        self.assertEqual(mock_import_in_progress.call_count, 1)
        self.assertEqual(mock_inventory.call_count, 0)

    @patch('akips.task.AKIPS')
    @patch('akips.task.is_snapshot_import_in_progress', return_value=False)
    def test_refresh_akips_devices_skips_when_akips_disabled(self, mock_import_in_progress, mock_akips):
        config = AKIPSConfiguration.get_solo()
        config.enabled = False
        config.save()

        refresh_akips_devices.run()

        self.assertEqual(mock_import_in_progress.call_count, 1)
        self.assertEqual(mock_akips.call_count, 0)

    @patch('akips.task.time.sleep')
    @patch('akips.task.AKIPS')
    @patch('akips.task.is_snapshot_import_in_progress', return_value=False)
    def test_refresh_akips_devices_resets_stale_critical_group(self, mock_import_in_progress, mock_akips, mock_sleep):
        config = AKIPSConfiguration.get_solo()
        config.enabled = True
        config.save()
        device = Device.objects.create(
            name='med-phillips-gateway.net.unc.edu',
            ip4addr='172.27.255.132',
            sysName='med-phillips-gateway.net.unc.edu',
            sysDescr='Gateway',
            sysLocation='Medical',
            group='Critical',
            tier='',
            building_name='',
            critical=True,
            type='Gateway',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=timezone.now() - timedelta(days=1),
        )

        mock_akips_instance = mock_akips.return_value
        mock_akips_instance.get_devices.return_value = {
            device.name: {
                'ip4addr': '172.27.255.132',
                'SNMPv2-MIB.sysName': 'med-phillips-gateway.net.unc.edu',
                'SNMPv2-MIB.sysDescr': 'Gateway',
                'SNMPv2-MIB.sysLocation': 'Medical',
            }
        }
        mock_akips_instance.get_maintenance_mode.return_value = []
        mock_akips_instance.get_group_membership.return_value = {
            device.name: ['2-Medical', '4-Phillips']
        }

        refresh_akips_devices.run()

        device.refresh_from_db()
        self.assertFalse(device.critical)
        self.assertEqual(device.group, 'default')
        self.assertEqual(device.tier, 'Medical')
        self.assertEqual(device.building_name, 'Phillips')
        self.assertTrue(device.notify)

    @patch('akips.task.EventManager')
    @patch('akips.task.is_snapshot_import_in_progress', return_value=False)
    def test_refresh_unreachable_skips_when_akips_disabled(self, mock_import_in_progress, mock_event_manager):
        config = AKIPSConfiguration.get_solo()
        config.enabled = False
        config.save()

        refresh_unreachable.run()

        self.assertEqual(mock_import_in_progress.call_count, 1)
        self.assertEqual(mock_event_manager.call_count, 0)

    def test_sanitize_snapshot_for_import_removes_unsupported_models(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as snapshot_file:
            json.dump([
                {'model': 'auth.permission', 'pk': 1, 'fields': {'name': 'Ignore me'}},
                {'model': 'akips.apiaccesskey', 'pk': 2, 'fields': {'name': 'Imported key'}},
                {'model': 'akips.device', 'pk': 3, 'fields': {'name': 'keep-me'}},
            ], snapshot_file)
            snapshot_path = snapshot_file.name

        sanitized_path = sanitize_snapshot_for_import(snapshot_path)
        self.addCleanup(lambda: os.path.exists(snapshot_path) and os.remove(snapshot_path))
        if sanitized_path != snapshot_path:
            self.addCleanup(lambda: os.path.exists(sanitized_path) and os.remove(sanitized_path))

        with open(sanitized_path, 'r', encoding='utf-8') as sanitized_file:
            sanitized_records = json.load(sanitized_file)

        self.assertEqual(len(sanitized_records), 1)
        self.assertEqual(sanitized_records[0]['model'], 'akips.device')

    def test_get_snapshot_import_models_skips_api_access_keys(self):
        model_labels = [model._meta.label_lower for model in get_snapshot_import_models()]

        self.assertNotIn('akips.apiaccesskey', model_labels)

    def test_sanitize_snapshot_for_import_strips_permission_fields(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as snapshot_file:
            json.dump([
                {
                    'model': 'auth.group',
                    'pk': 1,
                    'fields': {
                        'name': 'Operators',
                        'permissions': [['change_user', 'auth', 'user']],
                    },
                },
                {
                    'model': 'auth.user',
                    'pk': 2,
                    'fields': {
                        'username': 'viewer',
                        'groups': [1],
                        'user_permissions': [['change_user', 'auth', 'user']],
                    },
                },
            ], snapshot_file)
            snapshot_path = snapshot_file.name

        sanitized_path = sanitize_snapshot_for_import(snapshot_path, clear_existing_data=True)
        self.addCleanup(lambda: os.path.exists(snapshot_path) and os.remove(snapshot_path))
        if sanitized_path != snapshot_path:
            self.addCleanup(lambda: os.path.exists(sanitized_path) and os.remove(sanitized_path))

        with open(sanitized_path, 'r', encoding='utf-8') as sanitized_file:
            sanitized_records = json.load(sanitized_file)

        self.assertNotIn('permissions', sanitized_records[0]['fields'])
        self.assertNotIn('user_permissions', sanitized_records[1]['fields'])
        self.assertEqual(sanitized_records[1]['fields']['groups'], [1])

    def test_sanitize_snapshot_for_import_skips_auth_and_profiles_on_merge_import(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as snapshot_file:
            json.dump([
                {'model': 'auth.group', 'pk': 1, 'fields': {'name': 'Operators'}},
                {'model': 'auth.user', 'pk': 2, 'fields': {'username': 'viewer'}},
                {'model': 'akips.profile', 'pk': 3, 'fields': {'user': 2, 'alert_enabled': True, 'voice_enabled': False}},
                {'model': 'akips.device', 'pk': 4, 'fields': {'name': 'keep-me'}},
            ], snapshot_file)
            snapshot_path = snapshot_file.name

        sanitized_path = sanitize_snapshot_for_import(snapshot_path, clear_existing_data=False)
        self.addCleanup(lambda: os.path.exists(snapshot_path) and os.remove(snapshot_path))
        if sanitized_path != snapshot_path:
            self.addCleanup(lambda: os.path.exists(sanitized_path) and os.remove(sanitized_path))

        with open(sanitized_path, 'r', encoding='utf-8') as sanitized_file:
            sanitized_records = json.load(sanitized_file)

        self.assertEqual([record['model'] for record in sanitized_records], ['akips.device'])

    @patch('akips.models.Profile.objects.create')
    def test_create_profile_skips_raw_saves(self, mock_create):
        user = User(username='rawuser')

        create_profile(sender=User, instance=user, created=True, raw=True)

        self.assertEqual(mock_create.call_count, 0)

    @patch('akips.models.Profile.objects.create')
    def test_save_profile_skips_raw_saves(self, mock_create):
        user = User(username='rawuser')

        save_profile(sender=User, instance=user, raw=True)

        self.assertEqual(mock_create.call_count, 0)


class SummariesAPITests(TestCase):
    def setUp(self):
        self.url = reverse('summary_all')
        cache_delete_patcher = patch('akips.signals.cache.delete')
        self.mock_cache_delete = cache_delete_patcher.start()
        self.addCleanup(cache_delete_patcher.stop)
        self.user = User.objects.create_user(username='api-user', password='testpass123')
        self.summary = Summary.objects.create(
            type='Critical',
            name='Critical routers',
            ack=False,
            first_event=timezone.now(),
            last_event=timezone.now(),
            trend='New',
            status='Open',
        )

    def test_authenticated_session_can_access_summaries(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        self.assertEqual(payload['result'][0]['name'], 'Critical routers')

    def test_api_key_can_access_allowed_endpoint(self):
        access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Summaries consumer',
            allowed_endpoints=[APIAccessKey.Endpoint.SUMMARIES_READ],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        access_key.refresh_from_db()
        self.assertIsNotNone(access_key.last_used_at)
        self.assertTrue(check_password(raw_key, access_key.hashed_key))

    def test_api_key_without_scope_is_forbidden(self):
        _access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Unscoped consumer',
            allowed_endpoints=[],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'API key does not have access to this endpoint.')

    def test_missing_credentials_returns_unauthorized(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Authentication credentials were not provided.')

    def test_invalid_api_key_returns_unauthorized(self):
        response = self.client.get(self.url, HTTP_X_API_KEY='not-a-real-key')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid API key.')


class SummaryBatteryCleanupTests(TestCase):
    def setUp(self):
        cache_delete_patcher = patch('akips.signals.cache.delete')
        self.mock_cache_delete = cache_delete_patcher.start()
        self.addCleanup(cache_delete_patcher.stop)

        self.user = User.objects.create_user(username='summary-user', password='testpass123')
        self.device = Device.objects.create(
            name='ups-device-1',
            ip4addr='172.29.5.224',
            sysName='ups-device-1',
            sysDescr='UPS device',
            group='default',
            tier='ITS-Manning',
            building_name='Genetic-Medicine-Research-Building',
            critical=False,
            type='UPS',
            maintenance=False,
            hibernate=False,
            inventory_url='https://inventory.example.edu/ups-device-1',
            last_refresh=timezone.now(),
        )
        self.status = Status.objects.create(
            device=self.device,
            child='ups',
            attribute='UPS-MIB.upsOutputSource',
            index='3',
            value='normal',
            device_added=timezone.now(),
            last_change=timezone.now(),
            ip4addr='172.29.5.224',
        )
        self.summary = Summary.objects.create(
            type='Building',
            tier='ITS-Manning',
            name='Genetic-Medicine-Research-Building',
            ack=False,
            first_event=timezone.now(),
            last_event=timezone.now(),
            trend='Recovered',
            status='Closed',
        )
        self.summary.batteries.add(self.status)

    @patch('akips.ocnes.TDX')
    def test_refresh_summary_removes_stale_battery_associations(self, mock_tdx):
        mock_tdx.return_value.enabled = False

        EventManager().refresh_summary()

        self.summary.refresh_from_db()
        self.assertEqual(self.summary.batteries.count(), 0)

    @patch('akips.ocnes.TDX')
    def test_summary_view_does_not_show_normal_ups_as_battery_problem(self, mock_tdx):
        mock_tdx.return_value.enabled = False

        EventManager().refresh_summary()
        self.client.force_login(self.user)
        response = self.client.get(reverse('summary', args=[self.summary.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['batteries']), [])


class DevicesAPITests(TestCase):
    def setUp(self):
        self.url = reverse('devices_all')
        self.user = User.objects.create_user(username='devices-user', password='testpass123')
        Device.objects.create(
            name='device-a',
            ip4addr='192.0.2.10',
            sysName='device-a.example.edu',
            sysDescr='Example device',
            group='default',
            tier='Tier 1',
            building_name='ITS',
            critical=False,
            type='Switch',
            maintenance=False,
            hibernate=False,
            inventory_url='https://inventory.example.edu/device-a',
            last_refresh=timezone.now(),
        )

    def test_authenticated_session_can_access_devices(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        self.assertEqual(payload['result'][0]['name'], 'device-a')

    def test_api_key_can_access_devices(self):
        _access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Devices consumer',
            allowed_endpoints=[APIAccessKey.Endpoint.DEVICES_READ],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        self.assertEqual(payload['result'][0]['sysName'], 'device-a.example.edu')

    def test_devices_api_rejects_key_without_scope(self):
        _access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Wrong devices scope',
            allowed_endpoints=[APIAccessKey.Endpoint.SUMMARIES_READ],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'API key does not have access to this endpoint.')


class DeviceViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='device-viewer', password='testpass123')
        now = timezone.now()
        self.special_device = Device.objects.create(
            name='special-device',
            ip4addr='192.0.2.50',
            sysName='special-device.example.edu',
            sysDescr='Special grouping example',
            sysLocation='Campus',
            group='Servers',
            tier='Tier 3',
            building_name='Manning',
            critical=False,
            type='SERVER',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        self.critical_device = Device.objects.create(
            name='critical-device',
            ip4addr='192.0.2.51',
            sysName='critical-device.example.edu',
            sysDescr='Critical grouping example',
            sysLocation='Datacenter',
            group='Critical',
            tier='',
            building_name='',
            critical=True,
            type='ROUTER',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )

    def test_device_view_shows_special_grouping_value(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('device', args=[self.special_device.name]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Critical')
        self.assertContains(response, 'No')
        self.assertContains(response, 'Special Grouping')
        self.assertContains(response, 'Servers')

    def test_device_view_shows_critical_value_and_no_special_grouping(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('device', args=[self.critical_device.name]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Critical')
        self.assertContains(response, 'Yes')
        self.assertContains(response, 'Special Grouping')
        self.assertContains(response, 'None')


class RecentUsersViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = Users.as_view()
        self.viewer = User.objects.create_user(username='viewer', password='testpass123')
        self.recent_user = User.objects.create_user(username='recent-user', password='testpass123')

    def _create_session(self, session_data, expire_date):
        session = SessionStore()
        session.update(session_data)
        session.set_expiry(expire_date)
        session.save()
        return session

    def test_recent_users_uses_recorded_login_timestamp(self):
        now = timezone.now()
        login_at = now - timedelta(hours=2)
        last_activity = now - timedelta(minutes=15)
        expire_date = last_activity + timedelta(seconds=86400)
        self._create_session(
            {
                '_auth_user_id': str(self.recent_user.id),
                SESSION_LOGIN_AT_KEY: login_at.isoformat(),
            },
            expire_date,
        )

        request = self.factory.get(reverse('users'))
        request.user = self.viewer

        with patch('akips.views.timezone.now', return_value=now), patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(len(context['session_list']), 1)
        row = context['session_list'][0]
        self.assertEqual(row['user'], self.recent_user)
        self.assertEqual(row['login_at'], login_at)
        self.assertEqual(row['last_activity'], last_activity)
        self.assertEqual(row['duration_display'], '1 hour, 45 minutes, 0 seconds')

    def test_recent_users_falls_back_to_user_last_login(self):
        now = timezone.now()
        last_login = now - timedelta(hours=3)
        User.objects.filter(pk=self.recent_user.pk).update(last_login=last_login)
        self.recent_user.refresh_from_db()
        last_activity = now - timedelta(minutes=30)
        expire_date = last_activity + timedelta(seconds=86400)
        self._create_session(
            {'_auth_user_id': str(self.recent_user.id)},
            expire_date,
        )

        request = self.factory.get(reverse('users'))
        request.user = self.viewer

        with patch('akips.views.timezone.now', return_value=now), patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request)
            context = mock_render.call_args.kwargs['context']

        row = context['session_list'][0]
        self.assertEqual(row['login_at'], last_login)
        self.assertEqual(row['last_activity'], last_activity)
        self.assertEqual(row['duration_display'], '2 hours, 30 minutes, 0 seconds')

    def test_recent_users_skips_non_authenticated_sessions(self):
        now = timezone.now()
        expire_date = now + timedelta(hours=1)
        self._create_session({'some_key': 'some-value'}, expire_date)

        request = self.factory.get(reverse('users'))
        request.user = self.viewer

        with patch('akips.views.timezone.now', return_value=now), patch('akips.views.render') as mock_render:
            mock_render.return_value = object()
            self.view(request)
            context = mock_render.call_args.kwargs['context']

        self.assertEqual(context['session_list'], [])


class GroupingProblemsViewTests(TestCase):
    def setUp(self):
        self.page_url = reverse('devices_grouping_problems')
        self.api_url = reverse('devices_grouping_problems_data_api')
        self.user = User.objects.create_user(username='grouping-user', password='testpass123')
        now = timezone.now()

        Device.objects.create(
            name='problem-both-missing',
            ip4addr='192.0.2.30',
            sysName='problem-both-missing.example.edu',
            sysDescr='Needs grouping',
            group='default',
            tier='',
            building_name='',
            critical=False,
            type='',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        Device.objects.create(
            name='problem-building-missing',
            ip4addr='192.0.2.31',
            sysName='problem-building-missing.example.edu',
            sysDescr='Needs building grouping',
            group='default',
            tier='Tier 2',
            building_name='',
            critical=False,
            type='AP',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        Device.objects.create(
            name='valid-critical',
            ip4addr='192.0.2.40',
            sysName='valid-critical.example.edu',
            sysDescr='Critical device',
            group='Critical',
            tier='',
            building_name='',
            critical=True,
            type='Switch',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        Device.objects.create(
            name='valid-tier-building',
            ip4addr='192.0.2.41',
            sysName='valid-tier-building.example.edu',
            sysDescr='Fully grouped device',
            group='default',
            tier='Tier 1',
            building_name='ITS',
            critical=False,
            type='Switch',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        Device.objects.create(
            name='valid-special',
            ip4addr='192.0.2.42',
            sysName='valid-special.example.edu',
            sysDescr='Special grouping device',
            group='Servers',
            tier='',
            building_name='',
            critical=False,
            type='Server',
            maintenance=False,
            hibernate=False,
            notify=True,
            last_refresh=now,
        )
        Device.objects.create(
            name='valid-no-notify',
            ip4addr='192.0.2.43',
            sysName='valid-no-notify.example.edu',
            sysDescr='Notifications disabled',
            group='default',
            tier='',
            building_name='',
            critical=False,
            type='Router',
            maintenance=False,
            hibernate=False,
            notify=False,
            last_refresh=now,
        )

    def test_grouping_problems_page_requires_login(self):
        response = self.client.get(self.page_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_grouping_problems_page_renders(self):
        self.client.force_login(self.user)

        response = self.client.get(self.page_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grouping Problems')
        self.assertContains(response, 'Tier plus Building')
        self.assertContains(response, 'All types')
        self.assertContains(response, 'AP')
        self.assertContains(response, '(blank)')
        self.assertNotContains(response, '<th>Grouping</th>', html=True)

    def test_grouping_problems_api_returns_only_uncategorized_devices(self):
        self.client.force_login(self.user)

        response = self.client.get(self.api_url, {'draw': 1, 'start': 0, 'length': 25})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['recordsTotal'], 2)
        self.assertEqual(payload['recordsFiltered'], 2)
        self.assertEqual([row['name'] for row in payload['data']], ['problem-both-missing', 'problem-building-missing'])
        self.assertEqual(payload['data'][0]['grouping_issue'], 'Missing tier and building')
        self.assertEqual(payload['data'][1]['grouping_issue'], 'Missing building')

    def test_grouping_problems_api_search_filters_results(self):
        self.client.force_login(self.user)

        response = self.client.get(
            self.api_url,
            {
                'draw': 1,
                'start': 0,
                'length': 25,
                'search[value]': 'Tier 2',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['recordsTotal'], 2)
        self.assertEqual(payload['recordsFiltered'], 1)
        self.assertEqual([row['name'] for row in payload['data']], ['problem-building-missing'])

    def test_grouping_problems_api_type_filters_results(self):
        self.client.force_login(self.user)

        response = self.client.get(
            self.api_url,
            {
                'draw': 1,
                'start': 0,
                'length': 25,
                'type': 'AP',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['recordsTotal'], 2)
        self.assertEqual(payload['recordsFiltered'], 1)
        self.assertEqual([row['name'] for row in payload['data']], ['problem-building-missing'])

    def test_grouping_problems_api_blank_type_filters_results(self):
        self.client.force_login(self.user)

        response = self.client.get(
            self.api_url,
            {
                'draw': 1,
                'start': 0,
                'length': 25,
                'type': '__blank__',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['recordsTotal'], 2)
        self.assertEqual(payload['recordsFiltered'], 1)
        self.assertEqual([row['name'] for row in payload['data']], ['problem-both-missing'])


class UnreachablesAPITests(TestCase):
    def setUp(self):
        self.url = reverse('unreachables_all')
        self.user = User.objects.create_user(username='unreachables-user', password='testpass123')
        cache_delete_patcher = patch('akips.signals.cache.delete')
        self.mock_cache_delete = cache_delete_patcher.start()
        self.addCleanup(cache_delete_patcher.stop)
        self.device = Device.objects.create(
            name='device-b',
            ip4addr='192.0.2.20',
            sysName='device-b.example.edu',
            sysDescr='Example unreachable device',
            group='default',
            tier='Tier 2',
            building_name='Genome',
            critical=False,
            type='Switch',
            maintenance=False,
            hibernate=False,
            inventory_url='',
            last_refresh=timezone.now(),
        )
        Unreachable.objects.create(
            device=self.device,
            child='Ping',
            attribute='icmpEcho',
            ping_state='down',
            snmp_state='up',
            event_start=timezone.now(),
            status='Open',
            last_refresh=timezone.now(),
        )

    def test_authenticated_session_can_access_unreachables(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        self.assertEqual(payload['result'][0]['device__name'], 'device-b')

    def test_api_key_can_access_unreachables(self):
        _access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Unreachables consumer',
            allowed_endpoints=[APIAccessKey.Endpoint.UNREACHABLES_READ],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['result']), 1)
        self.assertEqual(payload['result'][0]['device__sysName'], 'device-b.example.edu')

    def test_unreachables_api_rejects_key_without_scope(self):
        _access_key, raw_key = APIAccessKey.create_with_generated_key(
            name='Wrong unreachable scope',
            allowed_endpoints=[APIAccessKey.Endpoint.DEVICES_READ],
        )

        response = self.client.get(self.url, HTTP_X_API_KEY=raw_key)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'API key does not have access to this endpoint.')


class DashboardCardsViewTests(TestCase):
    def setUp(self):
        self.url = reverse('dashboard_cards')
        self.user = User.objects.create_user(username='dashboard-user', password='testpass123')

    @patch('akips.views.get_card_data')
    def test_dashboard_cards_returns_signatures(self, mock_get_card_data):
        self.client.force_login(self.user)
        mock_get_card_data.side_effect = [
            {'rows': [], 'has_rows': False},
            {'rows': [], 'has_rows': False},
            {'rows': [], 'has_rows': False},
            {'rows': [], 'has_rows': False},
        ]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('cards', payload)
        self.assertIn('signatures', payload)
        self.assertEqual(set(payload['cards'].keys()), {'crit_card', 'bldg_card', 'spec_card', 'trap_card'})
        self.assertEqual(set(payload['signatures'].keys()), {'crit_card', 'bldg_card', 'spec_card', 'trap_card'})
