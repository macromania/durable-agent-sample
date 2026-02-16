"""Durable Task orchestrators implementing the saga pattern for travel bookings.

4 orchestrators:
- flight_booking_saga: book flight → pay → (compensate on failure)
- hotel_booking_saga:  book hotel  → pay → (compensate on failure)
- car_hire_booking_saga: book car  → pay → (compensate on failure)
- travel_booking_saga: compose all three as sub-orchestrations with full compensation
"""

import logging

from travel.activities import (
    book_flight_activity,
    book_hotel_activity,
    book_car_activity,
    process_flight_payment,
    process_hotel_payment,
    process_car_payment,
    cancel_flight_activity,
    cancel_hotel_activity,
    cancel_car_activity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual Booking Sagas (used standalone or as sub-orchestrations)
# ---------------------------------------------------------------------------

def flight_booking_saga(ctx, input: dict):
    """Book a flight and process payment. Compensate if payment fails.

    Input: {"destination": "Paris", "travel_date": "2026-03-01"}
    Returns: {"status": "success"|"failed", "booking": {...}, "payment": {...}}
    """
    destination = input["destination"]
    travel_date = input.get("travel_date")

    try:
        # Step 1: Book the flight
        booking = yield ctx.call_activity(
            book_flight_activity,
            input={"destination": destination, "travel_date": travel_date},
        )

        # Step 2: Process payment
        try:
            payment = yield ctx.call_activity(
                process_flight_payment,
                input=booking,
            )
        except Exception as pay_err:
            # Payment failed — compensate the booking
            logger.info(f"Flight payment failed: {pay_err}. Compensating booking...")
            yield ctx.call_activity(cancel_flight_activity, input=booking)
            return {
                "status": "failed",
                "service": "flight",
                "error": f"Payment failed: {pay_err}",
                "compensated": True,
            }

        return {
            "status": "success",
            "service": "flight",
            "booking": booking,
            "payment": payment,
        }

    except Exception as e:
        # Booking itself failed — nothing to compensate
        return {
            "status": "failed",
            "service": "flight",
            "error": str(e),
            "compensated": False,
        }


def hotel_booking_saga(ctx, input: dict):
    """Book a hotel and process payment. Compensate if payment fails.

    Input: {"destination": "Paris", "nights": 5, "check_in": "2026-03-01"}
    Returns: {"status": "success"|"failed", "booking": {...}, "payment": {...}}
    """
    destination = input["destination"]
    nights = input.get("nights", 3)
    check_in = input.get("check_in")

    try:
        # Step 1: Book the hotel
        booking = yield ctx.call_activity(
            book_hotel_activity,
            input={"destination": destination, "nights": nights, "check_in": check_in},
        )

        # Step 2: Process payment
        try:
            payment = yield ctx.call_activity(
                process_hotel_payment,
                input=booking,
            )
        except Exception as pay_err:
            logger.info(f"Hotel payment failed: {pay_err}. Compensating booking...")
            yield ctx.call_activity(cancel_hotel_activity, input=booking)
            return {
                "status": "failed",
                "service": "hotel",
                "error": f"Payment failed: {pay_err}",
                "compensated": True,
            }

        return {
            "status": "success",
            "service": "hotel",
            "booking": booking,
            "payment": payment,
        }

    except Exception as e:
        return {
            "status": "failed",
            "service": "hotel",
            "error": str(e),
            "compensated": False,
        }


def car_hire_booking_saga(ctx, input: dict):
    """Book a car hire and process payment. Compensate if payment fails.

    Input: {"destination": "Paris", "days": 5}
    Returns: {"status": "success"|"failed", "booking": {...}, "payment": {...}}
    """
    destination = input["destination"]
    days = input.get("days", 3)

    try:
        # Step 1: Book the car
        booking = yield ctx.call_activity(
            book_car_activity,
            input={"destination": destination, "days": days},
        )

        # Step 2: Process payment
        try:
            payment = yield ctx.call_activity(
                process_car_payment,
                input=booking,
            )
        except Exception as pay_err:
            logger.info(f"Car payment failed: {pay_err}. Compensating booking...")
            yield ctx.call_activity(cancel_car_activity, input=booking)
            return {
                "status": "failed",
                "service": "car",
                "error": f"Payment failed: {pay_err}",
                "compensated": True,
            }

        return {
            "status": "success",
            "service": "car",
            "booking": booking,
            "payment": payment,
        }

    except Exception as e:
        return {
            "status": "failed",
            "service": "car",
            "error": str(e),
            "compensated": False,
        }


# ---------------------------------------------------------------------------
# Full Travel Booking Saga — composes sub-orchestrations with compensation
# ---------------------------------------------------------------------------

def travel_booking_saga(ctx, input: dict):
    """Book a complete trip: flight + hotel + car hire.

    Runs each booking as a sub-orchestration. If any step fails,
    compensates all previously successful bookings in reverse order.

    Input: {"destination": "Paris", "nights": 5, "travel_date": "2026-03-01"}
    Returns: {"status": "success"|"failed", "bookings": {...}, ...}
    """
    destination = input["destination"]
    nights = input.get("nights", 3)
    travel_date = input.get("travel_date")

    # Track successful bookings for compensation
    completed = []  # [(result_dict, cancel_activity_fn)]

    # --- Step 1: Flight ---
    flight_result = yield ctx.call_sub_orchestrator(
        flight_booking_saga,
        input={"destination": destination, "travel_date": travel_date},
    )

    if flight_result["status"] != "success":
        return {
            "status": "failed",
            "stage": "flight",
            "error": flight_result.get("error", "Flight booking failed"),
            "compensations": [],
        }

    completed.append((flight_result, cancel_flight_activity))

    # --- Step 2: Hotel ---
    hotel_result = yield ctx.call_sub_orchestrator(
        hotel_booking_saga,
        input={"destination": destination, "nights": nights, "check_in": travel_date},
    )

    if hotel_result["status"] != "success":
        # Compensate flight
        compensations = []
        for prev_result, cancel_fn in reversed(completed):
            comp_input = {
                "confirmation": prev_result["booking"]["confirmation"],
                "payment_ref": prev_result["payment"]["payment_ref"],
            }
            comp_result = yield ctx.call_activity(cancel_fn, input=comp_input)
            compensations.append(comp_result)

        return {
            "status": "failed",
            "stage": "hotel",
            "error": hotel_result.get("error", "Hotel booking failed"),
            "compensations": compensations,
        }

    completed.append((hotel_result, cancel_hotel_activity))

    # --- Step 3: Car Hire ---
    car_result = yield ctx.call_sub_orchestrator(
        car_hire_booking_saga,
        input={"destination": destination, "days": nights},
    )

    if car_result["status"] != "success":
        # Compensate hotel + flight (reverse order)
        compensations = []
        for prev_result, cancel_fn in reversed(completed):
            comp_input = {
                "confirmation": prev_result["booking"]["confirmation"],
                "payment_ref": prev_result["payment"]["payment_ref"],
            }
            comp_result = yield ctx.call_activity(cancel_fn, input=comp_input)
            compensations.append(comp_result)

        return {
            "status": "failed",
            "stage": "car",
            "error": car_result.get("error", "Car hire booking failed"),
            "compensations": compensations,
        }

    # --- All succeeded! ---
    return {
        "status": "success",
        "destination": destination,
        "bookings": {
            "flight": flight_result,
            "hotel": hotel_result,
            "car": car_result,
        },
    }
