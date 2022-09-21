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
    path('summary/<id>/', views.SummaryView.as_view(), name='summary'),
    path('recent/', views.RecentSummaryView.as_view(), name='recent'),

    # Dynamic Content AJAX Views
    path('ajax/critcard/', views.CritCard.as_view(), name='crit_card'),
    path('ajax/tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('ajax/bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),
    path('ajax/trapcard/', views.TrapCard.as_view(), name='trap_card'),

    # API Update Views
    path('api/set_maintenance_mode', views.SetMaintenanceView.as_view(), name='set_maintenance'),
    path('ack/<summary_id>', views.AckView.as_view(), name='ack'),
    path('trap/<trap_id>/clear', views.ClearTrapView.as_view(), name='clear_trap'),
    #path('trap/<trap_id>/ack', views.AckTrapView.as_view(), name='ack_trap'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('webhook/', views.AKIPSListener.as_view(), name='akips_webhook'),
    path('webhook/', views.akips_webhook, name='akips_webhook'),

]