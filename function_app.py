import json
import logging
import os
import re
from typing import Annotated

from agent_framework import tool
from agent_framework.azure import AzureOpenAIChatClient, AgentFunctionApp
from azure.identity import AzureCliCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Azure OpenAI configuration
# ---------------------------------------------------------------------------

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
if not endpoint:
    raise ValueError("AZURE_OPENAI_ENDPOINT is not set.")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
tenant_id = os.getenv("AZURE_TENANT_ID")

credential = AzureCliCredential(tenant_id=tenant_id) if tenant_id else AzureCliCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")

# ---------------------------------------------------------------------------
# Durable Task Scheduler client — used by tools to start saga orchestrations
# ---------------------------------------------------------------------------

_dts_conn_str = os.getenv(
    "DURABLE_TASK_SCHEDULER_CONNECTION_STRING",
    "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None",
)


def _parse_connection_string(conn_str: str) -> dict:
    """Parse a DTS connection string into its components."""
    parts = {}
    for part in conn_str.split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            # Handle Endpoint which itself contains '='
            if key.strip().lower() == "endpoint":
                value = part.split("=", 1)[1]
            parts[key.strip().lower()] = value.strip()
    return parts


_conn = _parse_connection_string(_dts_conn_str)
_dts_endpoint = _conn.get("endpoint", "http://localhost:8080")
_dts_taskhub = _conn.get("taskhub", "default")

_dts_client = DurableTaskSchedulerClient(
    host_address=_dts_endpoint,
    secure_channel=not _dts_endpoint.startswith("http://localhost"),
    taskhub=_dts_taskhub,
    token_credential=None,
)


def _run_saga(orchestrator_name: str, input_data: dict, timeout: int = 120) -> str:
    """Schedule a saga orchestration and wait for completion. Returns JSON result."""
    instance_id = _dts_client.schedule_new_orchestration(
        orchestrator_name,
        input=input_data,
    )
    logger.info(f"Started orchestration '{orchestrator_name}': {instance_id}")

    state = _dts_client.wait_for_orchestration_completion(
        instance_id, timeout=timeout,
    )

    if state is None:
        return json.dumps({
            "status": "timeout",
            "instance_id": instance_id,
            "message": f"Orchestration did not complete within {timeout}s. "
            f"Check status at /api/travel-status/{instance_id}",
        })

    try:
        output = json.loads(state.serialized_output) if state.serialized_output else {}
    except json.JSONDecodeError:
        output = {"raw_output": state.serialized_output}

    output["instance_id"] = instance_id
    output["runtime_status"] = state.runtime_status.name
    return json.dumps(output)


# ---------------------------------------------------------------------------
# Agent tools — each triggers a saga orchestration via DTS client
# ---------------------------------------------------------------------------

@tool
def book_travel(
    destination: Annotated[str, "The travel destination city or country"],
    nights: Annotated[int, "Number of nights for the hotel stay"] = 3,
    travel_date: Annotated[str | None, "Travel date in YYYY-MM-DD format"] = None,
) -> str:
    """Book a complete trip including flight, hotel, and car hire.
    This runs the full travel booking saga which books all three services.
    If any booking or payment fails, all previous bookings are automatically
    cancelled and refunded (saga compensation pattern)."""
    return _run_saga("travel_booking_saga", {
        "destination": destination,
        "nights": nights,
        "travel_date": travel_date,
    })


@tool
def book_flight(
    destination: Annotated[str, "The flight destination city or country"],
    travel_date: Annotated[str | None, "Travel date in YYYY-MM-DD format"] = None,
) -> str:
    """Book a flight only. Includes flight reservation and payment processing.
    If payment fails, the flight reservation is automatically cancelled."""
    return _run_saga("flight_booking_saga", {
        "destination": destination,
        "travel_date": travel_date,
    })


@tool
def book_hotel(
    destination: Annotated[str, "The hotel destination city or country"],
    nights: Annotated[int, "Number of nights for the hotel stay"] = 3,
    check_in: Annotated[str | None, "Check-in date in YYYY-MM-DD format"] = None,
) -> str:
    """Book a hotel only. Includes hotel reservation and payment processing.
    If payment fails, the hotel reservation is automatically cancelled."""
    return _run_saga("hotel_booking_saga", {
        "destination": destination,
        "nights": nights,
        "check_in": check_in,
    })


@tool
def book_car_hire(
    destination: Annotated[str, "The car hire pickup city or country"],
    days: Annotated[int, "Number of days for the car hire"] = 3,
) -> str:
    """Book a car hire only. Includes car reservation and payment processing.
    If payment fails, the car reservation is automatically cancelled."""
    return _run_saga("car_hire_booking_saga", {
        "destination": destination,
        "days": days,
    })


# ---------------------------------------------------------------------------
# Travel Agent — front-door LLM agent with booking tools
# ---------------------------------------------------------------------------

TRAVEL_AGENT_INSTRUCTIONS = """\
You are a Travel Booking Assistant. You help users book flights, hotels, and car hire.

You have 4 tools available:
- **book_travel**: Book a complete trip (flight + hotel + car hire). Use this when the user
  wants a full travel package.
- **book_flight**: Book a flight only.
- **book_hotel**: Book a hotel only.
- **book_car_hire**: Book a car hire only.

When a user describes their travel needs:
1. Determine which service(s) they need (full trip, flight only, hotel only, or car only).
2. Extract the destination, dates, and duration from their request.
3. Call the appropriate tool(s).
4. Present the results clearly, including confirmation numbers, prices, and any failures.

If a booking fails, explain what happened and suggest alternatives. The system uses a saga
pattern — if part of a multi-service booking fails, previous bookings are automatically
cancelled and refunded.

Known failure scenarios (for testing):
- Flights to "Atlantis" always fail.
- Car hire in "Antarctica" always fails.
- Hotel stays longer than 14 nights always fail.
- There is a random chance of failure for any booking or payment.

Always be helpful and provide clear status updates about the booking process.
"""

agent = AzureOpenAIChatClient(
    endpoint=endpoint,
    deployment_name=deployment_name,
    ad_token=token.token,
).as_agent(
    instructions=TRAVEL_AGENT_INSTRUCTIONS,
    name="TravelAgent",
    tools=[book_travel, book_flight, book_hotel, book_car_hire],
)

# Configure the function app to host the agent with durable thread management
app = AgentFunctionApp(agents=[agent])
