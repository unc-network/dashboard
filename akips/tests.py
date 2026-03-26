from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, SimpleTestCase
from unittest.mock import patch

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
        self.assertEqual(context['hud_font_scale'], 1.9)

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

        self.assertEqual(context['hud_font_scale'], 1.9)

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
