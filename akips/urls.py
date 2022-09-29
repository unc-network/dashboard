from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='home'),
    path('unreachable/', views.UnreachableView.as_view(), name='unreachable'),

    # Event Focus Views
    path('summary/<id>/', views.SummaryView.as_view(), name='summary'),
    path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    path('builiding/<bldg>/', views.BuildingView.as_view(), name='building'),
    path('device/<name>/', views.DeviceView.as_view(), name='device'),
    path('trap/<trap_id>/', views.TrapView.as_view(), name='trap'),
    path('recent/', views.RecentSummaryView.as_view(), name='recent'),
    path('recent/unreachable', views.RecentUnreachablesView.as_view(), name='recent_unreachables'),
    path('recent/traps', views.RecentTrapsView.as_view(), name='recent_traps'),

    # Dynamic Content AJAX Views
    path('ajax/critcard/', views.CritCard.as_view(), name='crit_card'),
    path('ajax/tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('ajax/bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),
    path('ajax/trapcard/', views.TrapCard.as_view(), name='trap_card'),

    # API Update Views
    path('api/set_maintenance_mode', views.SetMaintenanceView.as_view(), name='set_maintenance'),
    path('api/summary/<summary_id>/ack', views.AckView.as_view(), name='ack'),
    path('api/trap/<trap_id>/ack', views.AckTrapView.as_view(), name='ack_trap'),
    path('api/trap/<trap_id>/clear', views.ClearTrapView.as_view(), name='clear_trap'),
    path('api/chart/', views.ChartDataView.as_view(), name='chart_data'),
    path('api/profile/', views.SetUserProfileView.as_view(), name='profile_api'),
    path('api/notifications/', views.UserAlertView.as_view(), name='api_notifications'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    path('incident/new', views.IncidentView.as_view(), name='create_incident'),
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('webhook/', views.AKIPSListener.as_view(), name='akips_webhook'),
    path('webhook/', views.akips_webhook, name='akips_webhook'),

]
