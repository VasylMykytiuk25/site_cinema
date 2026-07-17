from django.contrib import admin

from .models import Booking, BookingSeat, Genre, Hall, Movie, Session


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'genre', 'duration_minutes', 'age_rating', 'release_date', 'release_year', 'is_active')
    list_filter = ('genre', 'age_rating', 'is_active')
    search_fields = ('title', 'description', 'director', 'starring')


@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = ('name', 'rows_count', 'seats_per_row', 'total_seats')
    search_fields = ('name',)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('movie', 'hall', 'format_name', 'start_at', 'price', 'is_active', 'available_seats')
    list_filter = ('is_active', 'hall', 'movie', 'format_name')
    search_fields = ('movie__title', 'hall__name')
    date_hierarchy = 'start_at'


class BookingSeatInline(admin.TabularInline):
    model = BookingSeat
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session', 'tickets_count', 'total_price', 'status', 'booked_at')
    list_filter = ('status', 'booked_at')
    search_fields = ('user__username', 'session__movie__title')
    inlines = [BookingSeatInline]
