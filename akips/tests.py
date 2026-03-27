import json
import os
import tempfile

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from unittest.mock import patch

from .models import TDXConfiguration, InventoryConfiguration, create_profile, save_profile
from .task import SNAPSHOT_FIXTURE_LABELS, import_snapshot_task, refresh_inventory, sanitize_snapshot_for_import
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
