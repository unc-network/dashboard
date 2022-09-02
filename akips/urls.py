from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='akips_home'),

    # Event Focus Views
    #path('tier/<tier>/', views.TierView.as_view(), name='tier'),
    #path('builiding/<bldg>/', views.BldgView.as_view(), name='bldg'),
    #path('device/<name>/', views.DeviceView.as_view(), name='device'),

    # Hibernation Request
    #path('hibernation/', views.HibernationView.as_view(), name='hibernation'),

    # Incident Request
    #path('incident/', views.IncidentView.as_view(), name='incident'),

    # JSON Views
    #path('ajax/summary/', views.SummaryAJAX.as_view(), name='summary'),

    # Test
    path('task', views.TaskTest.as_view(), name='akips_tasktest'),
]