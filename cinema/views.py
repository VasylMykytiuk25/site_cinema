from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from dashboard.models import UserProfile

from .forms import BookingForm, MovieFilterForm
from .models import Booking, BookingSeat, Genre, Hall, Movie, Session
from .services import expire_pending_bookings


class BookingSyncMixin:
    def dispatch(self, request, *args, **kwargs):
        expire_pending_bookings()
        return super().dispatch(request, *args, **kwargs)


class SessionOverviewMixin:
    def _session_buckets(self):
        now = timezone.now()
        current_candidates = (
            Session.objects.filter(is_active=True, start_at__lte=now)
            .select_related("movie", "hall")
            .order_by("-start_at")[:12]
        )
        now_playing = []
        for session in current_candidates:
            ends_at = session.start_at + timedelta(minutes=session.movie.duration_minutes)
            if ends_at >= now:
                now_playing.append(session)

        upcoming = list(Session.objects.active()[:10])
        upcoming_today = [
            session
            for session in upcoming
            if timezone.localtime(session.start_at).date() == timezone.localdate()
        ]
        return {
            "now_playing": now_playing[:2],
            "upcoming_sessions": upcoming[:4],
            "today_sessions": upcoming_today[:6],
            "feature_movies": Movie.objects.filter(is_active=True)
            .exclude(source_url="")
            .select_related("genre")[:4],
        }


class HomeView(BookingSyncMixin, SessionOverviewMixin, TemplateView):
    template_name = "cinema/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._session_buckets())
        context["movie_count"] = Movie.objects.filter(is_active=True).exclude(source_url="").count()
        context["hall_count"] = Hall.objects.filter(sessions__isnull=False).distinct().count()
        return context


class MovieListView(BookingSyncMixin, SessionOverviewMixin, ListView):
    model = Movie
    template_name = "cinema/movie_list.html"
    context_object_name = "movies"
    paginate_by = 8

    def get_queryset(self):
        queryset = Movie.objects.filter(is_active=True).select_related("genre").exclude(source_url="")
        query = self.request.GET.get("q", "").strip()
        genre_id = self.request.GET.get("genre")
        hall_id = self.request.GET.get("hall")
        date_value = self.request.GET.get("date")

        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(description__icontains=query))
        if genre_id:
            queryset = queryset.filter(genre_id=genre_id)
        if hall_id:
            queryset = queryset.filter(sessions__hall_id=hall_id).distinct()
        if date_value:
            queryset = queryset.filter(sessions__start_at__date=date_value, sessions__is_active=True).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        halls = Hall.objects.filter(sessions__movie__source_url__isnull=False).distinct()
        context["filter_form"] = MovieFilterForm(
            self.request.GET or None,
            genres=Genre.objects.all(),
            halls=halls,
        )
        return context


class MovieDetailView(BookingSyncMixin, DetailView):
    model = Movie
    template_name = "cinema/movie_detail.html"
    context_object_name = "movie"

    def get_queryset(self):
        return Movie.objects.filter(is_active=True).select_related("genre").prefetch_related(
            Prefetch("sessions", queryset=Session.objects.active())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_hall = self.request.GET.get("hall", "").strip()
        sessions = list(self.object.sessions.all())
        hall_choices = []
        for session in sessions:
            if session.hall not in hall_choices:
                hall_choices.append(session.hall)

        if selected_hall:
            sessions = [session for session in sessions if str(session.hall_id) == selected_hall]

        grouped_sessions = {}
        for session in sessions:
            date_key = timezone.localtime(session.start_at).date()
            grouped_sessions.setdefault(date_key, []).append(session)

        context["grouped_sessions"] = grouped_sessions
        context["hall_choices"] = hall_choices
        context["selected_hall"] = selected_hall
        return context


def session_matrix(session):
    taken = {
        (seat.row_number, seat.seat_number)
        for seat in session.booked_seats.select_related("booking").exclude(
            booking__status=Booking.Status.CANCELLED
        )
    }
    hall = session.hall
    rows = []
    for row_number in range(1, hall.rows_count + 1):
        seats = []
        for seat_number in range(1, hall.seats_per_row + 1):
            status = "taken" if (row_number, seat_number) in taken else "free"
            seats.append(
                {
                    "row_number": row_number,
                    "seat_number": seat_number,
                    "code": f"{row_number}-{seat_number}",
                    "status": status,
                }
            )
        rows.append({"row_number": row_number, "seats": seats})
    return rows, taken


def seat_label(row_number, seat_number):
    return f"Ряд {row_number}, місце {seat_number}"


@login_required
def booking_create_view(request, session_id):
    expire_pending_bookings()
    session = get_object_or_404(
        Session.objects.select_related("movie", "hall"),
        pk=session_id,
        is_active=True,
    )

    if session.is_past:
        messages.error(request, "Цей сеанс уже завершився.")
        return redirect("cinema:movie_detail", pk=session.movie_id)

    seat_choices = [
        (f"{row}-{seat}", f"Ряд {row}, місце {seat}")
        for row in range(1, session.hall.rows_count + 1)
        for seat in range(1, session.hall.seats_per_row + 1)
    ]
    selected_codes = []

    if request.method == "POST":
        form = BookingForm(request.POST, seat_choices=seat_choices)
        if form.is_valid():
            selected_codes = form.cleaned_data["seats"]
            selected_seats = [tuple(map(int, seat.split("-"))) for seat in selected_codes]
            _, taken_seats = session_matrix(session)
            conflicted = [seat for seat in selected_seats if seat in taken_seats]

            if conflicted:
                conflicted_labels = ", ".join(seat_label(row, seat) for row, seat in conflicted)
                messages.error(
                    request,
                    f"Частина місць уже недоступна: {conflicted_labels}. Схему залу оновлено, обери інші місця.",
                )
            else:
                total_price = Decimal(len(selected_seats)) * session.price
                try:
                    with transaction.atomic():
                        booking = Booking.objects.create(
                            user=request.user,
                            session=session,
                            total_price=total_price,
                            status=Booking.Status.NEW,
                        )
                        for row_number, seat_number in selected_seats:
                            BookingSeat.objects.create(
                                booking=booking,
                                session=session,
                                row_number=row_number,
                                seat_number=seat_number,
                                price=session.price,
                            )
                except (IntegrityError, ValidationError):
                    messages.error(
                        request,
                        "Обрані місця вже були заброньовані іншим користувачем. Схему залу оновлено, спробуй ще раз.",
                    )
                else:
                    messages.success(
                        request,
                        "Бронювання створено. Воно очікує підтвердження адміністратором.",
                    )
                    return redirect("dashboard:my_bookings")
        else:
            selected_codes = request.POST.getlist("seats")
    else:
        form = BookingForm(seat_choices=seat_choices)

    rows, taken_seats = session_matrix(session)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    context = {
        "session": session,
        "rows": rows,
        "selected_seat_codes": selected_codes,
        "ticket_price": session.price,
        "form": form,
        "profile": profile,
        "taken_seats_count": len(taken_seats),
        "free_seats_count": session.available_seats,
    }
    return render(request, "cinema/booking_create.html", context)
