from django.urls import path

from . import views

urlpatterns = [

    # Main Views
    path('', views.Home.as_view(), name='home'),
    path('unreachable/', views.UnreachableView.as_view(), name='unreachable'),
    path('summary/<id>/', views.SummaryView.as_view(), name='summary'),
    path('trap/<trap_id>/', views.TrapView.as_view(), name='trap'),
    path('device/<name>/', views.DeviceView.as_view(), name='device'),
    path('devices/', views.Devices.as_view(), name='devices'),
    path('devices/maintenance', views.MaintenanceView.as_view(), name='maintenance'),
    path('batteries/', views.UPSProblems.as_view(), name='ups_problems'),
    path('users/', views.Users.as_view(), name='users'),
    path('preferences/', views.UserPreferences.as_view(), name='user_preferences'),

    # Event Focus Views
    #path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    #path('builiding/<bldg>/', views.BuildingView.as_view(), name='building'),
    path('recent/', views.RecentSummaryView.as_view(), name='recent'),
    path('recent/unreachable', views.RecentUnreachablesView.as_view(), name='recent_unreachables'),
    path('recent/traps', views.RecentTrapsView.as_view(), name='recent_traps'),

    # Dynamic Content AJAX Views
    path('ajax/critcard/', views.CritCard.as_view(), name='crit_card'),
    path('ajax/tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('ajax/bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),
    path('ajax/trapcard/', views.TrapCard.as_view(), name='trap_card'),
    path('ajax/speccard/', views.SpecialityCard.as_view(), name='spec_card'),

    # Device API
    path('api/devices/', views.DevicesAPI.as_view(), name='devices_all'),
    path('api/set_maintenance_mode', views.SetMaintenanceView.as_view(), name='set_maintenance'),
    path('api/status', views.StatusExportView.as_view(), name='status_export'),

    # Unreachables API
    path('api/unreachables/', views.UnreachablesAPI.as_view(), name='unreachables_all'),

    # Summary API
    path('api/summaries/', views.SummariesAPI.as_view(), name='summary_all'),
    #path('api/summary/<summary_id>/', views.SummaryAPI.as_view(), name='summary'),
    path('api/summary/<summary_id>/ack', views.AckView.as_view(), name='ack'),
    path('api/summary/<summary_id>/comment', views.SetComment.as_view(), name='set_comment'),
    # path('api/summary/<summary_id>/incident', views.SetIncident.as_view(), name='set_incident'),

    # Trap API
    path('api/trap/<trap_id>/ack', views.AckTrapView.as_view(), name='ack_trap'),
    path('api/trap/<trap_id>/clear', views.ClearTrapView.as_view(), name='clear_trap'),
    # path('api/trap/clear-all', views.ClearTrapView.as_view(), name='clear_trap_all'),

    # UX API
    path('api/chart/', views.ChartDataView.as_view(), name='chart_data'),
    path('api/notifications/', views.UserAlertView.as_view(), name='api_notifications'),
    path('api/profile/', views.SetUserProfileView.as_view(), name='profile_api'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Request Views
    path('incident/new', views.CreateIncidentView.as_view(), name='create_incident'),
    #path('incident/', views.IncidentView.as_view(), name='incident'),
    path('hibernate/', views.HibernateView.as_view(), name='hibernate'),
    path('hibernate/requests', views.HibernateRequestsView.as_view(), name='hibernate_requests'),

    # JSON Views
    #path('webhook/', views.AKIPSListener.as_view(), name='akips_webhook'),
    path('webhook/', views.akips_webhook, name='akips_webhook'),

]
