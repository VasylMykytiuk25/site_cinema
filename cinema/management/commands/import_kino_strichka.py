import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import Booking, BookingSeat, Genre, Hall, Movie, Session


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
)
BASE_URL = "https://kino-strichka.com"
SCHEDULE_URL = f"{BASE_URL}/schedule"
POSTERS_DIR = Path(settings.BASE_DIR) / "static" / "posters" / "kino_strichka"
PRICE_BY_FORMAT = {
    "2D": Decimal("180.00"),
    "3D Dolby": Decimal("220.00"),
}
DEFAULT_HALLS = [
    ("\u0417\u0430\u043b 1", 8, 12),
    ("\u0417\u0430\u043b 2", 7, 10),
    ("\u0417\u0430\u043b 3", 6, 9),
    ("\u0417\u0430\u043b 4", 9, 13),
    ("\u0417\u0430\u043b 5", 5, 8),
]
TRANSLIT_MAP = str.maketrans(
    {
        "\u0430": "a",
        "\u0431": "b",
        "\u0432": "v",
        "\u0433": "h",
        "\u0491": "g",
        "\u0434": "d",
        "\u0435": "e",
        "\u0454": "ie",
        "\u0436": "zh",
        "\u0437": "z",
        "\u0438": "y",
        "\u0456": "i",
        "\u0457": "i",
        "\u0439": "i",
        "\u043a": "k",
        "\u043b": "l",
        "\u043c": "m",
        "\u043d": "n",
        "\u043e": "o",
        "\u043f": "p",
        "\u0440": "r",
        "\u0441": "s",
        "\u0442": "t",
        "\u0443": "u",
        "\u0444": "f",
        "\u0445": "kh",
        "\u0446": "ts",
        "\u0447": "ch",
        "\u0448": "sh",
        "\u0449": "shch",
        "\u044c": "",
        "\u044e": "iu",
        "\u044f": "ia",
    }
)


class Command(BaseCommand):
    help = "Імпортує фільми з kino-strichka.com і генерує розклад на потрібний діапазон дат."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=5, help="Скільки днів розкладу з сайту взяти як шаблон.")
        parser.add_argument("--start-date", type=str, default="", help="Початкова дата у форматі YYYY-MM-DD.")
        parser.add_argument("--end-date", type=str, default="", help="Кінцева дата у форматі YYYY-MM-DD.")

    def handle(self, *args, **options):
        client = requests.Session()
        client.headers.update({"User-Agent": USER_AGENT})

        POSTERS_DIR.mkdir(parents=True, exist_ok=True)
        halls = self.prepare_halls()
        self.clear_existing_schedule()

        schedule_index = self.fetch_soup(client, SCHEDULE_URL)
        schedule_urls = self.collect_schedule_urls(schedule_index, limit=options["days"])
        start_date, end_date = self.resolve_date_range(options["start_date"], options["end_date"])

        movie_cache = {}
        day_patterns = []

        for schedule_url in schedule_urls:
            self.stdout.write(f"Обробка розкладу: {schedule_url}")
            soup = self.fetch_soup(client, schedule_url)
            pattern_entries = []
            for block_index, movie_block in enumerate(soup.select("div.flex.flex-col.gap-10 > div.flex.gap-6")):
                movie_link = movie_block.select_one('a[href^="/movies/"]')
                if not movie_link:
                    continue

                movie_url = urljoin(BASE_URL, movie_link["href"])
                if movie_url not in movie_cache:
                    movie_cache[movie_url] = self.import_movie(client, movie_url)
                movie = movie_cache[movie_url]
                pattern_entries.extend(self.extract_session_templates(movie, movie_block, block_index))

            if pattern_entries:
                day_patterns.append(pattern_entries)

        imported_sessions = self.generate_sessions(day_patterns, halls, start_date, end_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Імпорт завершено. Фільмів: {len(movie_cache)}, сеансів: {imported_sessions}, "
                f"період: {start_date} — {end_date}."
            )
        )

    def resolve_date_range(self, start_raw, end_raw):
        today = timezone.localdate()
        start_date = date.fromisoformat(start_raw) if start_raw else today
        end_date = date.fromisoformat(end_raw) if end_raw else start_date + timedelta(days=20)
        if end_date < start_date:
            raise ValueError("Кінцева дата не може бути раніше початкової.")
        return start_date, end_date

    def prepare_halls(self):
        halls = []
        for name, rows_count, seats_per_row in DEFAULT_HALLS:
            hall, created = Hall.objects.get_or_create(
                name=name,
                defaults={"rows_count": rows_count, "seats_per_row": seats_per_row},
            )
            if not created and (hall.rows_count != rows_count or hall.seats_per_row != seats_per_row):
                hall.rows_count = rows_count
                hall.seats_per_row = seats_per_row
                hall.save(update_fields=["rows_count", "seats_per_row"])
            halls.append(hall)
        return halls

    def clear_existing_schedule(self):
        source_movies = Movie.objects.exclude(source_url="")
        BookingSeat.objects.filter(session__movie__in=source_movies).delete()
        Booking.objects.filter(session__movie__in=source_movies).delete()
        Session.objects.filter(movie__in=source_movies).delete()

    def fetch_soup(self, client, url):
        response = client.get(url, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def collect_schedule_urls(self, soup, limit):
        urls = []
        for link in soup.select('a[href^="/schedule?date="]'):
            full_url = urljoin(BASE_URL, link["href"])
            if full_url not in urls:
                urls.append(full_url)
        return urls[:limit] or [SCHEDULE_URL]

    def import_movie(self, client, movie_url):
        soup = self.fetch_soup(client, movie_url)
        payload = self.extract_movie_payload(soup)

        genres = [item.strip() for item in payload.get("genre", "").split(",") if item.strip()]
        primary_genre_name = genres[0] if genres else "Інше"
        genre, _ = Genre.objects.get_or_create(name=primary_genre_name)

        release_date = payload.get("datePublished") or "2026-01-01"
        movie, _ = Movie.objects.update_or_create(
            title=payload.get("name", "Без назви").strip(),
            defaults={
                "description": payload.get("description", "").strip(),
                "duration_minutes": self.parse_duration(payload.get("duration")),
                "release_date": release_date,
                "release_year": self.parse_year(release_date),
                "age_rating": self.normalize_age_rating(payload.get("contentRating")),
                "genre": genre,
                "genres_text": ", ".join(genres),
                "director": self.extract_detail_value(soup, "Режисер"),
                "starring": self.extract_detail_value(soup, "У головних ролях"),
                "source_url": movie_url,
                "is_active": True,
            },
        )

        image_url = urljoin(BASE_URL, payload.get("image", ""))
        poster_relative = self.download_poster(client, movie.title, image_url)
        if poster_relative:
            movie.poster_static = poster_relative
            movie.save(update_fields=["poster_static"])

        return movie

    def extract_movie_payload(self, soup):
        script = soup.find("script", attrs={"type": "application/ld+json"})
        if not script:
            return {}
        raw = script.get_text(strip=True)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group(0)) if match else {}

    def extract_detail_value(self, soup, label):
        labels = soup.find_all(string=re.compile(rf"^\s*{re.escape(label)}\s*$"))
        for raw_label in labels:
            block = raw_label.find_parent()
            if not block or not block.parent:
                continue
            values = [text.strip() for text in block.parent.stripped_strings if text.strip()]
            if label in values:
                index = values.index(label)
                if index + 1 < len(values):
                    return values[index + 1]
        return ""

    def parse_duration(self, raw_value):
        match = re.search(r"(\d+)", str(raw_value or ""))
        return int(match.group(1)) if match else 90

    def parse_year(self, raw_date):
        match = re.match(r"(\d{4})", str(raw_date or ""))
        return int(match.group(1)) if match else None

    def normalize_age_rating(self, raw_rating):
        value = str(raw_rating or "").strip()
        if not value:
            return "0+"
        return value if value.endswith("+") else f"{value}+"

    def slugify_title(self, title):
        normalized = title.lower().translate(TRANSLIT_MAP)
        slug = re.sub(r"[^a-z0-9]+", "-", normalized)
        return slug.strip("-") or "movie"

    def download_poster(self, client, title, image_url):
        if not image_url:
            return ""
        extension = Path(image_url.split("?")[0]).suffix or ".jpg"
        filename = f"{self.slugify_title(title)}{extension}"
        destination = POSTERS_DIR / filename
        if not destination.exists():
            response = client.get(image_url, timeout=30)
            response.raise_for_status()
            destination.write_bytes(response.content)
        return (Path("posters") / "kino_strichka" / filename).as_posix()

    def extract_session_templates(self, movie, movie_block, block_index):
        templates = []
        for format_block in movie_block.select("div.mt-2.flex.flex-col.sm\\:flex-row.items-baseline.flex-wrap.gap-x-6"):
            format_header = format_block.find("h3")
            if not format_header:
                continue
            format_name = " ".join(format_header.stripped_strings)
            time_tags = format_block.find_all("time", attrs={"datetime": True})
            for slot_index, time_tag in enumerate(time_tags):
                raw_datetime = time_tag["datetime"]
                if not re.match(r"^\d{4}-\d{2}-\d{2}T", raw_datetime):
                    continue
                start_dt = datetime.fromisoformat(raw_datetime.replace("Z", "+00:00"))
                local_dt = timezone.localtime(start_dt)
                templates.append(
                    {
                        "movie": movie,
                        "format_name": format_name,
                        "show_time": local_dt.time().replace(second=0, microsecond=0),
                        "block_index": block_index,
                        "slot_index": slot_index,
                    }
                )
        return templates

    def pick_hall(self, halls, format_name, block_index, slot_index, day_offset):
        if format_name == "3D Dolby":
            return halls[(1 + day_offset) % len(halls)]
        return halls[(block_index + slot_index + day_offset) % len(halls)]

    def generate_sessions(self, day_patterns, halls, start_date, end_date):
        if not day_patterns:
            return 0

        imported_count = 0
        total_days = (end_date - start_date).days + 1
        current_tz = timezone.get_current_timezone()

        for day_offset in range(total_days):
            target_date = start_date + timedelta(days=day_offset)
            pattern = day_patterns[day_offset % len(day_patterns)]
            for entry in pattern:
                hall = self.pick_hall(
                    halls,
                    entry["format_name"],
                    entry["block_index"],
                    entry["slot_index"],
                    day_offset,
                )
                start_at = timezone.make_aware(
                    datetime.combine(target_date, entry["show_time"]),
                    current_tz,
                )
                Session.objects.create(
                    movie=entry["movie"],
                    hall=hall,
                    start_at=start_at,
                    format_name=entry["format_name"],
                    price=PRICE_BY_FORMAT.get(entry["format_name"], Decimal("180.00")),
                    is_active=True,
                )
                imported_count += 1

        return imported_count
