# Revised Architecture — Client/Worker Split

```
┌─────────────────────────────────────────────────────────┐
│  function_app.py (Azure Functions - CLIENT)             │
│                                                         │
│  TravelAgent (LLM, 4 tools)                            │
│    ├── book_travel(destination, nights)                  │
│    ├── book_flight(destination, date)                    │
│    ├── book_hotel(destination, nights)                   │
│    └── book_car_hire(destination, days)                  │
│                                                         │
│  Each tool → DurableTaskSchedulerClient                 │
│    .schedule_new_orchestration("xxx_saga", input={...})  │
│    .wait_for_orchestration_completion(id, timeout=60)    │
│    → returns result to agent → agent responds in NL     │
│                                                         │
│  GET /api/travel-status/{instance_id}                   │
│    → polls orchestration state, returns status JSON     │
└─────────────────────────┬───────────────────────────────┘
                          │ gRPC (Durable Task Scheduler)
┌─────────────────────────▼───────────────────────────────┐
│  travel_worker.py (Standalone - WORKER)                 │
│                                                         │
│  DurableTaskSchedulerWorker                             │
│    ├── travel_booking_saga                              │
│    │     ├── sub: flight_booking_saga                    │
│    │     ├── sub: hotel_booking_saga                     │
│    │     └── sub: car_hire_booking_saga                  │
│    │     (compensates in reverse on failure)             │
│    │                                                     │
│    ├── flight_booking_saga                               │
│    │     ├── book_flight_activity (LLM ~20% fail)       │
│    │     ├── process_flight_payment (~10% fail)          │
│    │     └── cancel_flight_activity (compensation)       │
│    │                                                     │
│    ├── hotel_booking_saga                                │
│    │     ├── book_hotel_activity (LLM ~15% fail)        │
│    │     ├── process_hotel_payment (~10% fail)           │
│    │     └── cancel_hotel_activity (compensation)        │
│    │                                                     │
│    └── car_hire_booking_saga                             │
│          ├── book_car_activity (LLM ~25% fail)          │
│          ├── process_car_payment (~10% fail)             │
│          └── cancel_car_activity (compensation)          │
│                                                         │
│  Dummy LLM Agents (FlightAgent, HotelAgent, CarAgent)  │
│    → Call Azure OpenAI to generate realistic             │
│      confirmations or rejection messages                 │
└─────────────────────────────────────────────────────────┘
```

## Each Sub-Orchestration Saga Flow

```
flight_booking_saga:
  1. book_flight_activity → LLM FlightAgent generates confirmation or fails (~20%)
  2. process_flight_payment → fake payment processing, random fail (~10%)
  If step 2 fails → cancel_flight_activity (undo step 1)
  If step 1 fails → return error immediately (nothing to compensate)
```

Same pattern for hotel and car hire.

## `travel_booking_saga` Compensation Flow

```
  1. yield call_sub_orchestrator(flight_booking_saga) → success ✓
  2. yield call_sub_orchestrator(hotel_booking_saga)  → success ✓
  3. yield call_sub_orchestrator(car_hire_booking_saga) → FAILS ✗
  
  Compensate in reverse:
    → cancel_hotel_activity (undo step 2)
    → cancel_flight_activity (undo step 1)
  Return {status: "failed", error: "...", compensations: [...]}
```

## Files

| File | Role |
|---|---|
| function_app.py | **Modified** — TravelAgent with 4 tools + `/api/travel-status/{id}` endpoint; tools use `DurableTaskSchedulerClient` |
| `travel_worker.py` | **New** — Standalone worker entry point; registers all orchestrators/activities, runs `DurableTaskSchedulerWorker` |
| `travel/sagas.py` | **New** — 4 orchestrator generators with saga/compensation logic |
| `travel/activities.py` | **New** — 9 activities: 3 booking + 3 payment + 3 cancellation |
| `travel/llm_agents.py` | **New** — 3 dummy LLM agent helpers that call Azure OpenAI |
| `travel/__init__.py` | **New** — Package init |

## How to Run

```bash
# Terminal 1: Start the worker
python travel_worker.py

# Terminal 2: Start the function app (client)
func start
```

## Example User Interaction

```
User: "I need a trip to Paris for 5 nights"
Agent: [calls book_travel tool] → schedules travel_booking_saga
       → waits for completion → gets result
Agent: "Great news! Your trip to Paris is booked:
        ✈ Flight: FL-20260216143022 (confirmed, $450)
        🏨 Hotel: HT-20260216143025 (5 nights, $875)  
        🚗 Car: CR-20260216143028 (5 days, $225)
        💳 All payments processed successfully.
        
        Track status: /api/travel-status/abc-123"

User: "Just get me a flight to Tokyo"
Agent: [calls book_flight tool] → schedules flight_booking_saga only
```
