"""Durable Task activities for travel booking sagas.

9 activities total:
- 3 booking activities (call LLM agents to simulate external systems)
- 3 payment activities (fake payment processing with ~10% failure)
- 3 cancellation activities (compensation/rollback)
"""

import logging
import random
from datetime import datetime

from travel.llm_agents import flight_agent_book, hotel_agent_book, car_agent_book

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Booking Activities — call LLM agents to simulate external systems
# ---------------------------------------------------------------------------

def book_flight_activity(ctx, input: dict) -> dict:
    """Book a flight using the LLM FlightAgent."""
    destination = input["destination"]
    travel_date = input.get("travel_date")
    logger.info(f"[Activity] Booking flight to {destination}...")

    result = flight_agent_book(destination=destination, travel_date=travel_date)

    if not result.get("success"):
        error_msg = result.get("error", "Flight booking failed")
        logger.error(f"[Activity] Flight booking failed: {error_msg}")
        raise Exception(f"Flight booking failed: {error_msg}")

    logger.info(f"[Activity] Flight booked: {result.get('confirmation')}")
    return result


def book_hotel_activity(ctx, input: dict) -> dict:
    """Book a hotel using the LLM HotelAgent."""
    destination = input["destination"]
    nights = input.get("nights", 3)
    check_in = input.get("check_in")
    logger.info(f"[Activity] Booking hotel in {destination} for {nights} nights...")

    result = hotel_agent_book(destination=destination, nights=nights, check_in=check_in)

    if not result.get("success"):
        error_msg = result.get("error", "Hotel booking failed")
        logger.error(f"[Activity] Hotel booking failed: {error_msg}")
        raise Exception(f"Hotel booking failed: {error_msg}")

    logger.info(f"[Activity] Hotel booked: {result.get('confirmation')}")
    return result


def book_car_activity(ctx, input: dict) -> dict:
    """Book a rental car using the LLM CarHireAgent."""
    destination = input["destination"]
    days = input.get("days", 3)
    logger.info(f"[Activity] Booking car hire in {destination} for {days} days...")

    result = car_agent_book(destination=destination, days=days)

    if not result.get("success"):
        error_msg = result.get("error", "Car hire booking failed")
        logger.error(f"[Activity] Car hire booking failed: {error_msg}")
        raise Exception(f"Car hire booking failed: {error_msg}")

    logger.info(f"[Activity] Car hired: {result.get('confirmation')}")
    return result


# ---------------------------------------------------------------------------
# Payment Activities — fake payment processing with ~10% random failure
# ---------------------------------------------------------------------------

def process_flight_payment(ctx, input: dict) -> dict:
    """Process payment for a flight booking. ~10% chance of failure."""
    confirmation = input.get("confirmation", "unknown")
    price = input.get("price", random.randint(150, 900))
    logger.info(f"[Payment] Processing flight payment for {confirmation}: ${price}...")

    if random.random() < 0.10:
        logger.error(f"[Payment] Flight payment DECLINED for {confirmation}")
        raise Exception(
            f"Payment declined for flight {confirmation}. "
            f"Card ending in **4242 was rejected by the payment processor."
        )

    payment_ref = f"PAY-FL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    logger.info(f"[Payment] Flight payment successful: {payment_ref}")
    return {
        "payment_ref": payment_ref,
        "amount": price,
        "currency": "USD",
        "status": "completed",
        "booking_ref": confirmation,
    }


def process_hotel_payment(ctx, input: dict) -> dict:
    """Process payment for a hotel booking. ~10% chance of failure."""
    confirmation = input.get("confirmation", "unknown")
    price = input.get("total_price", random.randint(240, 3500))
    logger.info(f"[Payment] Processing hotel payment for {confirmation}: ${price}...")

    if random.random() < 0.10:
        logger.error(f"[Payment] Hotel payment DECLINED for {confirmation}")
        raise Exception(
            f"Payment declined for hotel {confirmation}. "
            f"Insufficient funds on card ending in **4242."
        )

    payment_ref = f"PAY-HT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    logger.info(f"[Payment] Hotel payment successful: {payment_ref}")
    return {
        "payment_ref": payment_ref,
        "amount": price,
        "currency": "USD",
        "status": "completed",
        "booking_ref": confirmation,
    }


def process_car_payment(ctx, input: dict) -> dict:
    """Process payment for a car hire booking. ~10% chance of failure."""
    confirmation = input.get("confirmation", "unknown")
    price = input.get("total_price", random.randint(90, 840))
    logger.info(f"[Payment] Processing car payment for {confirmation}: ${price}...")

    if random.random() < 0.10:
        logger.error(f"[Payment] Car payment DECLINED for {confirmation}")
        raise Exception(
            f"Payment declined for car hire {confirmation}. "
            f"Card verification failed for card ending in **4242."
        )

    payment_ref = f"PAY-CR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    logger.info(f"[Payment] Car payment successful: {payment_ref}")
    return {
        "payment_ref": payment_ref,
        "amount": price,
        "currency": "USD",
        "status": "completed",
        "booking_ref": confirmation,
    }


# ---------------------------------------------------------------------------
# Cancellation Activities — compensating transactions
# ---------------------------------------------------------------------------

def cancel_flight_activity(ctx, input: dict) -> dict:
    """Compensating action: cancel a flight booking and refund payment."""
    confirmation = input.get("confirmation", "unknown")
    payment_ref = input.get("payment_ref")
    logger.info(f"[Compensate] Cancelling flight {confirmation}...")
    if payment_ref:
        logger.info(f"[Compensate] Refunding flight payment {payment_ref}")
    return {
        "cancelled": True,
        "booking_ref": confirmation,
        "refunded_payment": payment_ref,
        "service": "flight",
    }


def cancel_hotel_activity(ctx, input: dict) -> dict:
    """Compensating action: cancel a hotel booking and refund payment."""
    confirmation = input.get("confirmation", "unknown")
    payment_ref = input.get("payment_ref")
    logger.info(f"[Compensate] Cancelling hotel {confirmation}...")
    if payment_ref:
        logger.info(f"[Compensate] Refunding hotel payment {payment_ref}")
    return {
        "cancelled": True,
        "booking_ref": confirmation,
        "refunded_payment": payment_ref,
        "service": "hotel",
    }


def cancel_car_activity(ctx, input: dict) -> dict:
    """Compensating action: cancel a car hire booking and refund payment."""
    confirmation = input.get("confirmation", "unknown")
    payment_ref = input.get("payment_ref")
    logger.info(f"[Compensate] Cancelling car hire {confirmation}...")
    if payment_ref:
        logger.info(f"[Compensate] Refunding car payment {payment_ref}")
    return {
        "cancelled": True,
        "booking_ref": confirmation,
        "refunded_payment": payment_ref,
        "service": "car",
    }
