from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('chat/', views.chat_page, name='chat'),
    path('process_message/', views.process_message, name='process_message'),
]