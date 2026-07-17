from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema.models import Booking, BookingSeat, Genre, Hall, Movie, Session
from cinema.services import cancel_booking


User = get_user_model()


class CinemaModelTests(TestCase):
    def setUp(self):
        self.genre = Genre.objects.create(name="Драма")
        self.movie = Movie.objects.create(
            title="Тестовий фільм",
            description="Опис тестового фільму",
            duration_minutes=120,
            release_date=timezone.localdate(),
            age_rating="12+",
            genre=self.genre,
            is_active=True,
        )
        self.hall = Hall.objects.create(name="Зал Test", rows_count=3, seats_per_row=4)
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            start_at=timezone.now() + timezone.timedelta(days=1),
            price=Decimal("150.00"),
            is_active=True,
        )
        self.user = User.objects.create_user(username="viewer", password="pass12345")

    def test_movie_poster_url_uses_static_path(self):
        self.movie.poster_static = "posters/test-poster.jpg"
        self.movie.save(update_fields=["poster_static"])

        self.assertEqual(self.movie.poster_url, "/static/posters/test-poster.jpg")

    def test_session_available_seats_decreases_after_booking(self):
        booking = Booking.objects.create(
            user=self.user,
            session=self.session,
            total_price=Decimal("150.00"),
        )
        BookingSeat.objects.create(
            booking=booking,
            session=self.session,
            row_number=1,
            seat_number=1,
            price=Decimal("150.00"),
        )

        self.assertEqual(self.session.available_seats, 11)


class CinemaServiceTests(TestCase):
    def setUp(self):
        self.genre = Genre.objects.create(name="Трилер")
        self.movie = Movie.objects.create(
            title="Скасоване бронювання",
            description="Опис",
            duration_minutes=95,
            release_date=timezone.localdate(),
            age_rating="16+",
            genre=self.genre,
            is_active=True,
        )
        self.hall = Hall.objects.create(name="Зал Service", rows_count=2, seats_per_row=2)
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            start_at=timezone.now() + timezone.timedelta(hours=2),
            price=Decimal("200.00"),
            is_active=True,
        )
        self.user = User.objects.create_user(username="buyer", password="pass12345")

    def test_cancel_booking_marks_status_and_removes_seats(self):
        booking = Booking.objects.create(
            user=self.user,
            session=self.session,
            total_price=Decimal("200.00"),
        )
        BookingSeat.objects.create(
            booking=booking,
            session=self.session,
            row_number=1,
            seat_number=2,
            price=Decimal("200.00"),
        )

        cancel_booking(booking)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(booking.seats.count(), 0)


class BookingViewTests(TestCase):
    def setUp(self):
        self.genre = Genre.objects.create(name="Комедія")
        self.movie = Movie.objects.create(
            title="Сторінка бронювання",
            description="Опис",
            duration_minutes=100,
            release_date=timezone.localdate(),
            age_rating="0+",
            genre=self.genre,
            is_active=True,
        )
        self.hall = Hall.objects.create(name="Зал View", rows_count=2, seats_per_row=3)
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            start_at=timezone.now() + timezone.timedelta(days=1),
            price=Decimal("175.00"),
            is_active=True,
        )
        self.user = User.objects.create_user(username="guest", password="pass12345")

    def test_booking_page_requires_login(self):
        url = reverse("cinema:booking_create", kwargs={"session_id": self.session.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:login"), response.url)

    def test_booking_page_is_available_for_authenticated_user(self):
        self.client.login(username="guest", password="pass12345")
        url = reverse("cinema:booking_create", kwargs={"session_id": self.session.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вибір місць")
