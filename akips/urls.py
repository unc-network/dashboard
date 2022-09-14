from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='home'),
    path('unreachable/', views.UnreachableView.as_view(), name='unreachable'),

    # Event Focus Views
    path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    path('builiding/<bldg>/', views.BuildingView.as_view(), name='building'),
    path('device/<name>/', views.DeviceView.as_view(), name='device'),

    # API Update Views
    path('api/set_maintenance_mode', views.SetMaintenanceView.as_view(), name='set_maintenance'),

    # Dynamic Card Views
    path('api/critcard/', views.CritCard.as_view(), name='crit_card'),
    path('api/tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('api/bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('webhook/', views.AKIPSListener.as_view(), name='akips_webhook'),
    path('webhook/', views.akips_webhook, name='akips_webhook'),

]