from django.urls import path
from django.contrib.auth import views as auth
from snippets import views
urlpatterns = [path('', views.home, name='home'), path('register/', views.register, name='register'), path('login/', auth.LoginView.as_view(), name='login'), path('logout/', auth.LogoutView.as_view(), name='logout'), path('new/', views.edit, name='new'), path('snippets/<int:pk>/edit/', views.edit, name='edit'), path('snippets/<int:pk>/delete/', views.delete, name='delete'), path('snippets/<int:pk>/favorite/', views.favorite, name='favorite'), path('sw.js', views.service_worker), path('health/', views.health)]
