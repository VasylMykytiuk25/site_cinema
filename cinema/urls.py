from django.urls import path

from .views import HomeView, MovieDetailView, MovieListView, booking_create_view

app_name = 'cinema'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('movies/', MovieListView.as_view(), name='movie_list'),
    path('movies/<int:pk>/', MovieDetailView.as_view(), name='movie_detail'),
    path('booking/<int:session_id>/', booking_create_view, name='booking_create'),
]
