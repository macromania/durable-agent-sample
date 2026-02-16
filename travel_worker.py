"""Travel booking worker — standalone Durable Task Scheduler worker.

Registers all saga orchestrators and activities, then runs the worker.
Start this separately from the Azure Functions app (function_app.py).

Usage:
    python travel_worker.py

Environment variables:
    ENDPOINT           — Durable Task Scheduler endpoint (default: http://localhost:8080)
    TASKHUB            — Task hub name (default: default)
    AZURE_OPENAI_ENDPOINT     — Azure OpenAI endpoint (required for LLM agents)
    AZURE_OPENAI_DEPLOYMENT_NAME — Model deployment (default: gpt-4o-mini)
"""

import asyncio
import logging
import os

from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

from travel.sagas import (
    travel_booking_saga,
    flight_booking_saga,
    hotel_booking_saga,
    car_hire_booking_saga,
)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")
    taskhub = os.getenv("TASKHUB", "default")

    logger.info("Starting Travel Booking Saga worker...")
    print(f"  Endpoint: {endpoint}")
    print(f"  TaskHub:  {taskhub}")

    with DurableTaskSchedulerWorker(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub,
        token_credential=None,
    ) as w:
        # Register orchestrators
        w.add_orchestrator(travel_booking_saga)
        w.add_orchestrator(flight_booking_saga)
        w.add_orchestrator(hotel_booking_saga)
        w.add_orchestrator(car_hire_booking_saga)

        # Register booking activities
        w.add_activity(book_flight_activity)
        w.add_activity(book_hotel_activity)
        w.add_activity(book_car_activity)

        # Register payment activities
        w.add_activity(process_flight_payment)
        w.add_activity(process_hotel_payment)
        w.add_activity(process_car_payment)

        # Register cancellation/compensation activities
        w.add_activity(cancel_flight_activity)
        w.add_activity(cancel_hotel_activity)
        w.add_activity(cancel_car_activity)

        w.start()
        logger.info("Worker started. Registered orchestrators: "
                    "travel_booking_saga, flight_booking_saga, "
                    "hotel_booking_saga, car_hire_booking_saga")
        logger.info("Press Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")

    logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
