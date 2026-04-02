import json
import os
import tempfile

from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from .models import TDXConfiguration, InventoryConfiguration, AKIPSConfiguration, APIAccessKey, Summary, create_profile, save_profile
from .task import (
    SNAPSHOT_FIXTURE_LABELS,
    import_snapshot_task,
    refresh_inventory,
    refresh_akips_devices,
    refresh_unreachable,
    sanitize_snapshot_for_import,
)
from .views import Home

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

    @patch('akips.views.import_snapshot_task.delay')
    @patch('akips.views.Settings._persist_uploaded_snapshot')
    def test_staff_can_import_snapshot(self, mock_persist_snapshot, mock_import_delay):
        self.client.force_login(self.staff_user)
        mock_persist_snapshot.return_value = '/tmp/mock-snapshot.json'
        upload = SimpleUploadedFile('snapshot.json', b'[]', content_type='application/json')

        response = self.client.post(
            self.url,
            {'action': 'import_snapshot', 'snapshot_file': upload},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.url)
        self.assertEqual(mock_persist_snapshot.call_count, 1)
        self.assertEqual(mock_import_delay.call_count, 1)
        self.assertEqual(mock_import_delay.call_args.args, ('/tmp/mock-snapshot.json',))
        self.assertEqual(mock_import_delay.call_args.kwargs, {'clear_existing_data': False})

    @patch('akips.views.import_snapshot_task.delay')
    @patch('akips.views.Settings._persist_uploaded_snapshot')
    def test_import_can_clear_existing_data(self, mock_persist_snapshot, mock_import_delay):
        self.client.force_login(self.staff_user)
        mock_persist_snapshot.return_value = '/tmp/mock-snapshot.json'
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
        self.assertEqual(mock_persist_snapshot.call_count, 1)
        self.assertEqual(mock_import_delay.call_count, 1)
        self.assertEqual(mock_import_delay.call_args.args, ('/tmp/mock-snapshot.json',))
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

    @patch('akips.task.os.path.exists', return_value=False)
    @patch('akips.task.cache.delete')
    @patch('akips.task.call_command')
    @patch('akips.task.clear_snapshot_import_targets')
    @patch('akips.task.sanitize_snapshot_for_import', return_value='/tmp/mock-snapshot-sanitized.json')
    @patch('akips.task.cache.add', return_value=True)
    def test_import_snapshot_task_uses_lock(self, mock_cache_add, mock_sanitize_snapshot, mock_clear_targets, mock_call_command, mock_cache_delete, mock_exists):
        import_snapshot_task.run('/tmp/mock-snapshot.json', clear_existing_data=True)

        self.assertEqual(mock_cache_add.call_count, 1)
        self.assertEqual(mock_cache_add.call_args.args, ('snapshot_import_task', True, 14400))
        self.assertEqual(mock_sanitize_snapshot.call_count, 1)
        self.assertEqual(mock_sanitize_snapshot.call_args.args, ('/tmp/mock-snapshot.json',))
        self.assertEqual(mock_sanitize_snapshot.call_args.kwargs, {'clear_existing_data': True})
        self.assertEqual(mock_clear_targets.call_count, 1)
        self.assertEqual(mock_call_command.call_count, 1)
        self.assertEqual(mock_call_command.call_args.args, ('loaddata', '/tmp/mock-snapshot-sanitized.json'))
        self.assertEqual(mock_cache_delete.call_count, 1)
        self.assertEqual(mock_cache_delete.call_args.args, ('snapshot_import_task',))

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
                {'model': 'akips.device', 'pk': 2, 'fields': {'name': 'keep-me'}},
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
