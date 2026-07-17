from datetime import timedelta

from django.utils import timezone

from .models import Booking


AUTO_CANCEL_MINUTES = 300


def cancel_booking(booking):
    if booking.status != Booking.Status.CANCELLED:
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status'])
    booking.seats.all().delete()
    return booking


def expire_pending_bookings():
    cutoff = timezone.now() + timedelta(minutes=AUTO_CANCEL_MINUTES)
    bookings = Booking.objects.filter(
        status=Booking.Status.NEW,
        session__start_at__lte=cutoff,
    ).prefetch_related('seats')
    count = 0
    for booking in bookings:
        cancel_booking(booking)
        count += 1
    return count
