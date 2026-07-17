from django.urls import path

from .views import (
    MyBookingsView,
    ProfileView,
    RegisterView,
    StaffBookingListView,
    StaffSessionCreateView,
    UserLoginView,
    UserLogoutView,
    staff_booking_update_view,
)

app_name = 'dashboard'

urlpatterns = [
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('my-bookings/', MyBookingsView.as_view(), name='my_bookings'),
    path('staff/bookings/', StaffBookingListView.as_view(), name='staff_bookings'),
    path('staff/bookings/<int:pk>/<str:action>/', staff_booking_update_view, name='staff_booking_update'),
    path('staff/sessions/create/', StaffSessionCreateView.as_view(), name='staff_sessions'),
]
