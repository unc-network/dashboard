from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='akips_home'),

    # Specific Views
    #path('tier/<tier>/', views.TierView.as_view(), name='tier_view'),
    #path('builiding/<bldg>/', views.BldgView.as_view(), name='bldg_view'),
    #path('device/<name>/', views.DeviceView.as_view(), name='device_view'),

    # JSON Views
    #path('ajax/summary/', views.SummaryAJAX.as_view(), name='summary'),

    # Test
    path('task', views.TaskTest.as_view(), name='akips_tasktest'),
]