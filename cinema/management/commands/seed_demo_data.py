from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import Genre, Hall, Movie, Session


class Command(BaseCommand):
    help = 'Створює початкові жанри, фільми, зали та сеанси.'

    def handle(self, *args, **options):
        genres = {
            'Наукова фантастика': Genre.objects.get_or_create(name='Наукова фантастика')[0],
            'Драма': Genre.objects.get_or_create(name='Драма')[0],
            'Анімація': Genre.objects.get_or_create(name='Анімація')[0],
            'Трилер': Genre.objects.get_or_create(name='Трилер')[0],
        }

        movies_data = [
            {
                'title': 'Космічний рубіж',
                'genre': genres['Наукова фантастика'],
                'description': 'Екіпаж дослідників вирушає до далекої колонії та стикається з невідомим сигналом, що змінює хід місії.',
                'duration_minutes': 128,
                'release_date': date(2025, 11, 14),
                'age_rating': '16+',
            },
            {
                'title': 'Листи до світанку',
                'genre': genres['Драма'],
                'description': 'Історія про вибір, втрати й другий шанс, що розгортається в невеликому прибережному місті.',
                'duration_minutes': 112,
                'release_date': date(2025, 9, 4),
                'age_rating': '12+',
            },
            {
                'title': 'Місто хмар',
                'genre': genres['Анімація'],
                'description': 'Підліток і його механічний друг вирушають у небезпечну подорож між повітряними островами.',
                'duration_minutes': 96,
                'release_date': date(2025, 12, 19),
                'age_rating': '0+',
            },
        ]

        created_movies = []
        for movie_data in movies_data:
            movie, _ = Movie.objects.get_or_create(
                title=movie_data['title'],
                defaults=movie_data,
            )
            created_movies.append(movie)

        hall_red, _ = Hall.objects.get_or_create(name='Зал Red', defaults={'rows_count': 6, 'seats_per_row': 8})
        hall_blue, _ = Hall.objects.get_or_create(name='Зал Blue', defaults={'rows_count': 7, 'seats_per_row': 10})

        now = timezone.localtime()
        session_specs = [
            (created_movies[0], hall_red, now + timedelta(hours=5), Decimal('180.00')),
            (created_movies[0], hall_blue, now + timedelta(days=1, hours=3), Decimal('210.00')),
            (created_movies[1], hall_red, now + timedelta(days=1, hours=6), Decimal('160.00')),
            (created_movies[2], hall_blue, now + timedelta(days=2, hours=4), Decimal('190.00')),
        ]

        for movie, hall, start_at, price in session_specs:
            Session.objects.get_or_create(
                movie=movie,
                hall=hall,
                start_at=start_at.replace(minute=0, second=0, microsecond=0),
                defaults={'price': price, 'is_active': True},
            )

        self.stdout.write(self.style.SUCCESS('Демонстраційні дані створено або оновлено.'))
