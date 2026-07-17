from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from cinema.models import Booking, Hall
from cinema.services import cancel_booking, expire_pending_bookings

from .forms import LoginForm, ProfileForm, RegisterForm, StaffSessionForm
from .models import UserProfile


DEFAULT_HALLS = [
    ("\u0417\u0430\u043b 1", 8, 12),
    ("\u0417\u0430\u043b 2", 7, 10),
    ("\u0417\u0430\u043b 3", 6, 9),
]


class UserLoginView(LoginView):
    template_name = "dashboard/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("cinema:movie_list")


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "dashboard/register.html"
    success_url = reverse_lazy("cinema:movie_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Реєстрація пройшла успішно.")
        return response


class MyBookingsView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = "dashboard/my_bookings.html"
    context_object_name = "bookings"

    def dispatch(self, request, *args, **kwargs):
        expire_pending_bookings()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user)
            .select_related("session", "session__movie", "session__hall")
            .prefetch_related("seats")
        )


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "dashboard/profile.html"
    success_url = reverse_lazy("dashboard:profile")

    def get_object(self, queryset=None):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Профіль оновлено.")
        return super().form_valid(form)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class StaffBookingListView(StaffRequiredMixin, ListView):
    model = Booking
    template_name = "dashboard/staff_bookings.html"
    context_object_name = "bookings"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        expire_pending_bookings()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            Booking.objects.select_related("user", "session", "session__movie", "session__hall")
            .prefetch_related("seats")
        )
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status"] = self.request.GET.get("status", "").strip()
        context["status_choices"] = Booking.Status.choices
        return context


class StaffSessionCreateView(StaffRequiredMixin, CreateView):
    form_class = StaffSessionForm
    template_name = "dashboard/staff_session_form.html"
    success_url = reverse_lazy("dashboard:staff_sessions")

    def dispatch(self, request, *args, **kwargs):
        expire_pending_bookings()
        self.ensure_default_halls()
        return super().dispatch(request, *args, **kwargs)

    def ensure_default_halls(self):
        for name, rows, seats in DEFAULT_HALLS:
            hall, created = Hall.objects.get_or_create(
                name=name,
                defaults={"rows_count": rows, "seats_per_row": seats},
            )
            if not created and (hall.rows_count != rows or hall.seats_per_row != seats):
                hall.rows_count = rows
                hall.seats_per_row = seats
                hall.save(update_fields=["rows_count", "seats_per_row"])

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Сеанс створено.")
        return response


@user_passes_test(lambda user: user.is_staff)
def staff_booking_update_view(request, pk, action):
    expire_pending_bookings()
    booking = get_object_or_404(Booking, pk=pk)
    if request.method == "POST":
        if action == "confirm":
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status"])
            messages.success(request, "Бронювання підтверджено.")
        elif action == "cancel":
            cancel_booking(booking)
            messages.success(request, "Бронювання скасовано.")
    return redirect("dashboard:staff_bookings")
