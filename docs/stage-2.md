## Stage 2: Human-in-the-Loop Administrator Approval

Stage 2 extends the parking chatbot from Stage 1 by adding a human administrator approval workflow.

The reservation is sent to the administrator when chatbot collects and validates all reservation details. The administrator can then approve or reject the request via REST API. The chatbot then can show the decisions of admin to the user. The chatbot and the administrator agent can communicate with the approval service, but they cannot approve or reject reservations themselves.

---

## Features

Stage 2 adds the following featu:
- second LangChain agent for communication with the administrator;
- automatic submission of completed reservations for administrator approval;
- REST API for administrator approval requests;
- human approval and rejection of reservation requests;
- reservation status tracking;
- administrator comments;
- communication between the main chatbot and administrator agent;
- user requests for checking reservation status;
- error handling when the administrator service is unavailable;
- automated tests for the administrator workflow.

---

## System Architecture

```text
                    User
                      │
                      ▼
              Parking Chatbot
                 (Agent 1)
                      │
                      ▼
              Reservation Flow
                      │
                      ▼
        ReservationApprovalIntegration
                      │
                      ▼
                ApprovalGateway
                      │
                      ▼
          LangChainApprovalGateway
                      │
                      ▼
        Administrator LangChain Agent
                 (Agent 2)
                      │
                      ▼
              LangChain Tools
                      │
                      ▼
       AdministratorApprovalClient
                      │
                      ▼
              FastAPI REST API
                      │
                      ▼
            Human Administrator
                      │
                Approve / Reject
```

The first agent is the parking chatbot. The second agent is implemented using LangChain, which needs to handle communication with the administrator approval service. It can submit a reservation for approval and check the status of an existing request. The final approval or rejection is always performed by human (aka administrator).

## Project Structute 
src/parking_chatbot/
├── admin/
│   ├── agent.py
│   ├── api.py
│   ├── client.py
│   ├── gateway.py
│   ├── integration.py
│   ├── models.py
│   └── repository.py
│
├── application.py
├── chatbot/
└── cli.py

tests/

├── test_admin_agent.py
├── test_admin_api.py
├── test_admin_approval.py
├── test_admin_client.py
├── test_admin_integration.py
└── test_application.py

### Main components

* agent.py - creates the second LangChain 
* api.py – provides the REST API 
* client.py – communicates with the administrator API through HTTP
* gateway.py – provides communication between the chatbot and the second agent
* integration.py – connects completed reservations from Agent 1 with the administrator approval workflow
* models.py – contains administrator approval models
* repository.py – stores approval requests
* application.py – connects all Stage 2 components when the application starts

## Administrator Agent
The second agent has two tools:
* submit_reservation_for_approval - sends a completed reservation to the administrator service.
* check_approval_status - retrieves the current status of an existing approval request.

The agent does not have tools for approving or rejecting reservations. 

## Reservation Approval Flow
``` text
User completes reservation
        ↓
Reservation is validated
        ↓
Agent 1 sends reservation to Agent 2
        ↓
Agent 2 submits approval request
        ↓
Administrator API creates request
        ↓
Status = pending
        ↓
Human administrator reviews request
        ↓
     ┌─────────┴─────────┐
     ▼                   ▼
  approved            rejected
     │                   │
     └─────────┬─────────┘
               ▼
     Chatbot checks status
               ↓
      User receives result
```

Each approval request receives a unique request ID, which is used to retrieve the administrator decision. 

## Human Administrator
The administrator service is implemented using FastAPI.

It can be started with:

```bash
python -m uvicorn parking_chatbot.admin.api:app --reload
```
The API documentation is available at: ```http://127.0.0.1:8000/docs ```

## Checking Reservation Status
After the administrator makes a decision, the user can ask the chatbot for the current reservation status. For now, the quesition that chat responds to is "What is the status of my reservation?".

## Installation and Setup
1. Start the administrator service in the first terminal:

``` bash 
python -m uvicorn parking_chatbot.admin.api:app --reload
```

2. Start the chatbot in the second terminal:
``` bash 
python -m parking_chatbot.cli --with-admin-approval
```

By default, the chatbot connects to ```http://127.0.0.1:8000```.

A different administrator service URL can be provided using:
``` bash
ADMIN_APPROVAL_BASE_URL=http://127.0.0.1:8000 \
python -m parking_chatbot.cli --with-admin-approval
```

## Current Limitations

The current Stage 2 implementation has several limitations:

* approval state is stored in memory and is lost when the administrator service restarts
* status updates are requested by the user rather than automatically pushed to the chatbot
* the CLI keeps one reservation approval workflow in memory
* intent detection is currently rule-based, so differently worded status questions may not always be recognized
* the administrator interface currently uses the FastAPI API documentation instead of a separate graphical interface.

These limitations do not affect the main Stage 2 Human-in-the-Loop workflow, but they would need to be addressed for a production system.






