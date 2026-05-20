from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('settings/', views.settings_view, name='settings'),
    path('skills/', views.skills_list, name='skills_list'),
    path('skills/<str:skill_name>/', views.skills_detail, name='skills_detail'),
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/create/', views.session_create, name='session_create'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
    path('sessions/<int:session_id>/step/', views.session_step_api, name='session_step_api'),
    path('workspace/', views.workspace_view, name='workspace'),
]
