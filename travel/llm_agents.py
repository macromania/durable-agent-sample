"""Dummy LLM agents that simulate flight, hotel, and car hire booking systems.

Each agent calls Azure OpenAI to generate realistic booking confirmations
or failure messages. Built-in random failure chance makes the system non-deterministic.
"""

import json
import logging
import os
import random
from datetime import datetime

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger(__name__)


def _get_openai_client() -> AzureOpenAI:
    """Create an Azure OpenAI client using environment variables."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT is not set.")

    credential = DefaultAzureCredential(
        exclude_managed_identity_credential=True,
    )
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )

    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_deployment=deployment,
        azure_ad_token_provider=token_provider,
        api_version="2024-12-01-preview",
    )


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Make a single LLM call and return the response text."""
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Flight Agent
# ---------------------------------------------------------------------------

def flight_agent_book(destination: str, travel_date: str | None = None) -> dict:
    """Simulate a flight booking via LLM. ~20% random failure chance,
    or guaranteed failure if destination is 'Atlantis'."""
    ref_id = f"FL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    should_fail = destination.lower() == "atlantis" or random.random() < 0.20

    if should_fail:
        reason = _call_llm(
            system_prompt=(
                "You are a flight booking system. The booking has FAILED. "
                "Generate a realistic failure message with an error reference number. "
                "Respond ONLY with a JSON object: {\"success\": false, \"error\": \"<message>\", \"ref\": \"<ref>\"}"
            ),
            user_prompt=f"Flight to {destination} on {travel_date or 'next available'}. Ref: {ref_id}",
        )
        try:
            result = json.loads(reason)
        except json.JSONDecodeError:
            result = {"success": False, "error": reason, "ref": ref_id}
        result["success"] = False
        return result

    confirmation = _call_llm(
        system_prompt=(
            "You are a flight booking system. The booking SUCCEEDED. "
            "Generate a realistic confirmation with flight number, departure time, "
            "gate, and a price between $150-$900. "
            "Respond ONLY with a JSON object: "
            "{\"success\": true, \"confirmation\": \"<ref>\", \"flight_number\": \"...\", "
            "\"departure\": \"...\", \"gate\": \"...\", \"price\": <number>, \"destination\": \"...\"}"
        ),
        user_prompt=f"Flight to {destination} on {travel_date or 'next available'}. Confirmation ref: {ref_id}",
    )
    try:
        result = json.loads(confirmation)
    except json.JSONDecodeError:
        result = {"success": True, "confirmation": ref_id, "destination": destination, "raw": confirmation}
    result["success"] = True
    result["confirmation"] = ref_id
    return result


# ---------------------------------------------------------------------------
# Hotel Agent
# ---------------------------------------------------------------------------

def hotel_agent_book(destination: str, nights: int = 3, check_in: str | None = None) -> dict:
    """Simulate a hotel booking via LLM. ~15% random failure chance,
    or guaranteed failure if nights > 14."""
    ref_id = f"HT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    should_fail = nights > 14 or random.random() < 0.15

    if should_fail:
        reason = _call_llm(
            system_prompt=(
                "You are a hotel reservation system. The booking has FAILED. "
                "Generate a realistic failure message (fully booked, dates unavailable, etc). "
                "Respond ONLY with a JSON object: {\"success\": false, \"error\": \"<message>\", \"ref\": \"<ref>\"}"
            ),
            user_prompt=f"Hotel in {destination}, {nights} nights from {check_in or 'tomorrow'}. Ref: {ref_id}",
        )
        try:
            result = json.loads(reason)
        except json.JSONDecodeError:
            result = {"success": False, "error": reason, "ref": ref_id}
        result["success"] = False
        return result

    confirmation = _call_llm(
        system_prompt=(
            "You are a hotel reservation system. The booking SUCCEEDED. "
            "Generate a realistic confirmation with hotel name, room type, "
            "check-in/check-out dates, and a total price ($80-$250/night). "
            "Respond ONLY with a JSON object: "
            "{\"success\": true, \"confirmation\": \"<ref>\", \"hotel_name\": \"...\", "
            "\"room_type\": \"...\", \"check_in\": \"...\", \"check_out\": \"...\", "
            "\"total_price\": <number>, \"destination\": \"...\"}"
        ),
        user_prompt=(
            f"Hotel in {destination}, {nights} nights from {check_in or 'tomorrow'}. "
            f"Confirmation ref: {ref_id}"
        ),
    )
    try:
        result = json.loads(confirmation)
    except json.JSONDecodeError:
        result = {"success": True, "confirmation": ref_id, "destination": destination, "raw": confirmation}
    result["success"] = True
    result["confirmation"] = ref_id
    return result


# ---------------------------------------------------------------------------
# Car Hire Agent
# ---------------------------------------------------------------------------

def car_agent_book(destination: str, days: int = 3) -> dict:
    """Simulate a car hire booking via LLM. ~25% random failure chance,
    or guaranteed failure if destination is 'Antarctica'."""
    ref_id = f"CR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    should_fail = destination.lower() == "antarctica" or random.random() < 0.25

    if should_fail:
        reason = _call_llm(
            system_prompt=(
                "You are a car rental system. The booking has FAILED. "
                "Generate a realistic failure message (no vehicles, location unsupported, etc). "
                "Respond ONLY with a JSON object: {\"success\": false, \"error\": \"<message>\", \"ref\": \"<ref>\"}"
            ),
            user_prompt=f"Car hire in {destination} for {days} days. Ref: {ref_id}",
        )
        try:
            result = json.loads(reason)
        except json.JSONDecodeError:
            result = {"success": False, "error": reason, "ref": ref_id}
        result["success"] = False
        return result

    confirmation = _call_llm(
        system_prompt=(
            "You are a car rental system. The booking SUCCEEDED. "
            "Generate a realistic confirmation with car type, pickup location, "
            "and a daily rate ($30-$120/day). "
            "Respond ONLY with a JSON object: "
            "{\"success\": true, \"confirmation\": \"<ref>\", \"car_type\": \"...\", "
            "\"pickup_location\": \"...\", \"daily_rate\": <number>, "
            "\"total_price\": <number>, \"destination\": \"...\"}"
        ),
        user_prompt=f"Car hire in {destination} for {days} days. Confirmation ref: {ref_id}",
    )
    try:
        result = json.loads(confirmation)
    except json.JSONDecodeError:
        result = {"success": True, "confirmation": ref_id, "destination": destination, "raw": confirmation}
    result["success"] = True
    result["confirmation"] = ref_id
    return result
