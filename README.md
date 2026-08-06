# Parking Reservation Chatbot

A parking reservation chatbot for the AI Engineering course. Meaning that an intelligent chatbot should help users reserve parking spaces and provide information using RAG.

The project was developed in four stages according to the given requireemnts:
1. RAG chatbot
2. Administrator approval
3. MCP reservation storage
4. LangGraph orchestration

## Features
The full project pipeline performs the following:
- Answers parking-related questions using RAG
- Collects reservation information
- Sends completed reservations to the administrator for approval
- Uses LangGraph to control the complete workflow
- Stores workflow state between separate user messages
- Automatically checks the administrator decision in the background
- Notifies the user when the reservation is approved or rejected in the chatbot
- Records approved reservations through the MCP server
- Allows to make multiple reservations in the same chatbot session
- Prevents two active reservations from overlapping
- Handles recording failures and allows retrying
- Performs integration and load testing of the complete workflow


## Documentation
The detailed metholodgy of each stage is given under `/docs` folder.

- [Stage 1: Creation of a RAG System and Chatbot](docs/stage-1.md)
- [Stage 2: Human-in-the-Loop Administrator Approval](docs/stage-2.md)
- [Stage 3: Processing confirmed reservation by using MCP server](docs/stage-3.md)
- [Stage 4: Orchestrating All Components via LangGraph](docs/stage-4.md)

## Installation and Setup
1. Python environment
``` bash
conda create --name parking-chatbot python=3.11 -y
conda activate parking-chatbot
```

2. Project installation
``` bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

3. LLM Configuration in `configs/openai.json`

4. Administrator API in the first terminal:
``` bash
python -m uvicorn parking_chatbot.admin.api:app --reload
```

If the administrator API uses a different address, configure:
``` bash
ADMIN_APPROVAL_BASE_URL=http://127.0.0.1:8000
```

5. Chatbot in the second terminal:
``` bash
python -m parking_chatbot.cli --with-langgraph
```

6. Chatbot interaction
As soon as the CLI for chatbot works, yiu can:
- ask the parking-related questions
- create a reservation (for example, "make reservation")

After all details are collected, the chatbot sends the reservation to the administrator and returns a request ID.

7. Request decision
- Open in the browser `http://127.0.0.1:8000/docs`
- Click on `GET /approval-requests` endpoint and clikc on "try it out"
- Paste the reservation ID, approve or reject, use the admin comments
- Select Execute

Within a few seconds, the chatbot should automatically display:
```text
Your reservation has been approved and recorded.
Request ID: ...
Administrator comment: Approved
```

8. MCP storage
To check the confirmed reservations file:
``` bash
cat data/dynamic/confirmed_reservations.txt
```

## Testing
- The complete test suite can be run with:
``` bash
python -m pytest
```
- Static checks can be run with:
``` bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
```

## Limitations
- The checkpointer uses InMemorySaver. Workflow state remains available while the application is running, but it is lost after the application restarts.
- The administrator repository is also stored in memory.
