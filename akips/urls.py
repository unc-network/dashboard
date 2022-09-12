from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='home'),
    path('unreachable/', views.UnreachableView.as_view(), name='unreachable'),

    # Event Focus Views
    path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    path('builiding/<bldg>/', views.BuildingView.as_view(), name='building'),
    path('device/<name>/', views.DeviceView.as_view(), name='device'),

    # Dynamic Card Views
    path('critcard/', views.CritCard.as_view(), name='crit_card'),
    path('tiercard/', views.TierCard.as_view(), name='tier_card'),
    path('bldgcard/', views.BuildingCard.as_view(), name='bldg_card'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('ajax/summary/', views.SummaryAJAX.as_view(), name='summary'),

]