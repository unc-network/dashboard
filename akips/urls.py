from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='home'),
    path('unreachable/', views.UnreachableView.as_view(), name='unreachable'),
    path('incident/', views.IncidentView.as_view(), name='incident'),

    # Event Focus Views
    path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    path('builiding/<bldg>/', views.BuildingView.as_view(), name='building'),
    path('device/<name>/', views.DeviceView.as_view(), name='device'),

    # Dynamic Content AJAX Views
    path('ajax/critcard/', views.CritCard.as_view(), name='crit_card'),
    path('ajax/tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('ajax/bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),

    # API Update Views
    path('api/set_maintenance_mode', views.SetMaintenanceView.as_view(), name='set_maintenance'),
    path('ack/<summary_id>', views.AckView.as_view(), name='ack'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('webhook/', views.AKIPSListener.as_view(), name='akips_webhook'),
    path('webhook/', views.akips_webhook, name='akips_webhook'),

]