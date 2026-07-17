from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Назва')

    class Meta:
        ordering = ['name']
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанри'

    def __str__(self):
        return self.name


class Movie(models.Model):
    title = models.CharField(max_length=200, verbose_name='Назва')
    description = models.TextField(verbose_name='Опис')
    poster = models.ImageField(upload_to='movies/posters/', blank=True, null=True, verbose_name='Постер')
    poster_static = models.CharField(max_length=255, blank=True, verbose_name='Постер у static')
    duration_minutes = models.PositiveIntegerField(verbose_name='Тривалість, хв')
    release_date = models.DateField(verbose_name='Дата виходу')
    release_year = models.PositiveIntegerField(blank=True, null=True, verbose_name='Рік')
    age_rating = models.CharField(max_length=10, verbose_name='Вікове обмеження')
    genre = models.ForeignKey(Genre, on_delete=models.PROTECT, related_name='movies', verbose_name='Жанр')
    genres_text = models.CharField(max_length=255, blank=True, verbose_name='Жанри текстом')
    director = models.CharField(max_length=255, blank=True, verbose_name='Режисер')
    starring = models.TextField(blank=True, verbose_name='У головних ролях')
    source_url = models.URLField(blank=True, verbose_name='Джерело')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Створено')
    is_active = models.BooleanField(default=True, verbose_name='Активний')

    class Meta:
        ordering = ['title']
        verbose_name = 'Фільм'
        verbose_name_plural = 'Фільми'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('cinema:movie_detail', kwargs={'pk': self.pk})

    @property
    def poster_url(self):
        if self.poster:
            return self.poster.url
        if self.poster_static:
            return f'/static/{self.poster_static}'
        return ''


class Hall(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Назва')
    rows_count = models.PositiveIntegerField(verbose_name='Кількість рядів')
    seats_per_row = models.PositiveIntegerField(verbose_name='Місць у ряді')

    class Meta:
        ordering = ['name']
        verbose_name = 'Зал'
        verbose_name_plural = 'Зали'

    def __str__(self):
        return f'{self.name} ({self.total_seats} місць)'

    @property
    def total_seats(self):
        return self.rows_count * self.seats_per_row


class SessionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, start_at__gte=timezone.now()).select_related('movie', 'hall')


class Session(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='sessions', verbose_name='Фільм')
    hall = models.ForeignKey(Hall, on_delete=models.PROTECT, related_name='sessions', verbose_name='Зал')
    start_at = models.DateTimeField(verbose_name='Початок сеансу')
    format_name = models.CharField(max_length=50, blank=True, verbose_name='Формат')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Ціна квитка')
    is_active = models.BooleanField(default=True, verbose_name='Активний')

    objects = SessionQuerySet.as_manager()

    class Meta:
        ordering = ['start_at']
        verbose_name = 'Сеанс'
        verbose_name_plural = 'Сеанси'

    def __str__(self):
        return f'{self.movie.title} - {timezone.localtime(self.start_at):%d.%m.%Y %H:%M}'

    @property
    def available_seats(self):
        occupied = self.booked_seats.exclude(booking__status=Booking.Status.CANCELLED).count()
        return self.hall.total_seats - occupied

    @property
    def is_past(self):
        return self.start_at < timezone.now()


class Booking(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Нове'
        CONFIRMED = 'confirmed', 'Підтверджено'
        CANCELLED = 'cancelled', 'Скасовано'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings', verbose_name='Користувач')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='bookings', verbose_name='Сеанс')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Загальна сума')
    booked_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата бронювання')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, verbose_name='Статус')

    class Meta:
        ordering = ['-booked_at']
        verbose_name = 'Бронювання'
        verbose_name_plural = 'Бронювання'

    def __str__(self):
        return f'Бронювання #{self.pk} - {self.user}'

    @property
    def tickets_count(self):
        return self.seats.count()


class BookingSeat(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='seats', verbose_name='Бронювання')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='booked_seats', verbose_name='Сеанс')
    row_number = models.PositiveIntegerField(verbose_name='Ряд')
    seat_number = models.PositiveIntegerField(verbose_name='Місце')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Ціна')

    class Meta:
        ordering = ['row_number', 'seat_number']
        verbose_name = 'Місце в бронюванні'
        verbose_name_plural = 'Місця в бронюванні'
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'row_number', 'seat_number'],
                name='unique_session_seat',
            ),
        ]

    def __str__(self):
        return f'Ряд {self.row_number}, місце {self.seat_number}'

    def clean(self):
        hall = self.session.hall
        if self.row_number > hall.rows_count or self.seat_number > hall.seats_per_row:
            raise ValidationError('Обране місце не існує у цьому залі.')

        if self.booking_id and self.booking.session_id != self.session_id:
            raise ValidationError('Сеанс місця має збігатися з сеансом бронювання.')

    def save(self, *args, **kwargs):
        if self.booking_id and not self.session_id:
            self.session = self.booking.session
        self.full_clean()
        return super().save(*args, **kwargs)
