from django.urls import path

from . import views

urlpatterns = [
    path('', views.Home.as_view(), name='akips_home'),
    path('task', views.TaskTest.as_view(), name='akips_tasktest'),
]