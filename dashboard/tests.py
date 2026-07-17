from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema.models import Booking, Genre, Hall, Movie, Session


User = get_user_model()


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="pass12345")
        self.staff = User.objects.create_user(
            username="manager",
            password="pass12345",
            is_staff=True,
        )

    def test_profile_page_requires_login(self):
        response = self.client.get(reverse("dashboard:profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:login"), response.url)

    def test_profile_page_is_available_for_authenticated_user(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("dashboard:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Редагування профілю")

    def test_staff_bookings_page_requires_staff_access(self):
        response = self.client.get(reverse("dashboard:staff_bookings"))

        self.assertEqual(response.status_code, 302)

        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("dashboard:staff_bookings"))

        self.assertEqual(response.status_code, 403)

    def test_staff_bookings_page_is_available_for_staff(self):
        self.client.login(username="manager", password="pass12345")
        response = self.client.get(reverse("dashboard:staff_bookings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Панель бронювань")


class DashboardBookingDisplayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member2", password="pass12345")
        self.genre = Genre.objects.create(name="Драма")
        self.movie = Movie.objects.create(
            title="Моє бронювання",
            description="Опис",
            duration_minutes=110,
            release_date=timezone.localdate(),
            age_rating="12+",
            genre=self.genre,
            is_active=True,
        )
        self.hall = Hall.objects.create(name="Зал Dashboard", rows_count=2, seats_per_row=2)
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            start_at=timezone.now() + timezone.timedelta(days=1),
            price=Decimal("180.00"),
            is_active=True,
        )
        self.booking = Booking.objects.create(
            user=self.user,
            session=self.session,
            total_price=Decimal("180.00"),
        )

    def test_my_bookings_page_shows_user_booking(self):
        self.client.login(username="member2", password="pass12345")
        response = self.client.get(reverse("dashboard:my_bookings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Мої бронювання")
        self.assertContains(response, "Моє бронювання")
