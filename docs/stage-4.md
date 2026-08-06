## Stage 3: Orchestrating All Components via LangGraph
The goal of Stage 4 was to combine all previously implemented components into one workflow using LangGraph. 

## System Architecture

```text
                         User
                           │
                           ▼
                    Parking Chatbot
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
         RAG Pipeline              Reservation Flow
              │                         │
              ▼                         ▼
         Milvus Vector DB       LangGraph Orchestration
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                         ▼              ▼              ▼
                User Interaction   Administrator    Recording
                     Node              Node            Node
                                        │              │
                                        ▼              ▼
                                  Administrator     MCP Client
                                      API              │
                                        │              ▼
                                        ▼          MCP Server
                               Approve / Reject         │
                                                        ▼
                                         confirmed_reservations.txt

```

The scheme above shows that chatbot first processes the user message. Parking-related questions are answered using RAG. If the user starts a reservation, the chatbot collects all required details. After the reservation is complete, LangGraph sends it to the administrator node. If the reservation is still pending, the workflow waits for the administrator decision. If it is approved, the workflow continues to the recording node. The recording node sends the data to the MCP server, which writes the reservation to the text file.

## Stage 4 Main folders
* src/parking_chatbot/orchestration/ – LangGraph state, nodes, graph, workflow service, monitoring, serialization, and recording adapter

## LangGraph Workflow
LangGraph uses a shared state to pass information between nodes.

The state contains:
* current operation;
* user message;
* chatbot response;
* workflow route;
* reservation details;
* approval request ID;
* administrator approval status;
* approval time;
* administrator comment;
* recording status;
* safe workflow error message.

The state is saved through LangGraph’s InMemorySaver.

Values stored in the checkpoint:

* UUID values are stored as strings;
* dates and times are stored in ISO format;
* enum values are stored as strings;
* reservation data is stored as a plain dictionary.

### User Interaction Node
The user interaction node delegates the user message to the existing ParkingChatbot. The node checks whether a new reservation was completed during the current turn. If no reservation was completed, the graph ends after returning the chatbot response. If a reservation was completed, the graph sends it to the administrator node.

### Administrator Node

Administrator node's responsibilities are:
* submitting a new reservation for approval;
* checking the current status of an existing request;
* preserving the approval request ID;
* preserving the administrator comment;
* preserving the real decision time;
* deciding whether the workflow should finish or continue to recording;

The possible statuses are: 
* pending - waits for a later status update
* approved - ontinues to the recording node
* rejected - finishes without calling the MCP server


### Recording Node

The recording node runs only when the administrator approves the reservation.

It receives:
* reservation details;
* approval request ID;
* administrator decision time.

The node delegates recording to `MCPConfirmedReservationRecorder`. The recorder creates a `ConfirmedReservation` object and calls the existing MCP client. The MCP client starts the MCP server over the standard input/output transport. 

### Sequential Reservations

The same CLI session can process more than one reservation. After a reservation reaches a final status, a new reservation starts with new graph instance and new approval request ID. This prevents the next reservation from receiving data from the previous one. If the user tries to create another reservation while the current one is still pending, the system returns: `Your current reservation is still waiting for administrator approval. Please wait for a decision before starting another reservation.`.

### Status Requests

The latest reservation status remains available after the workflow is completed.

The chatbot can answer questions as:
* What is the status of my reservation?
* Is my reservation approved?
* Was my booking rejected?
* Was my reservation recorded?

Then, new reservationcan begin only when the user clearly asks to make another reservation.

## Load Testing
A lightweight load-testing module was implemented using Python’s ThreadPoolExecutor. It does not call the real Azure OpenAI API and does not download external models. 

The load tests cover four scenarios:
1. Chatbot
    * tests concurrent user interactions;
    * checks thread isolation;
    * uses the real orchestration service.
2. Administrator
    * uses the real FastAPI application;
    * creates, approves, and retrieves multiple requests;
    * checks unique request IDs and correct decisions.
3. MCP Storage
    * uses the real MCP tool;
    * uses the real file repository;
    * verifies concurrent writes and duplicate protection;
    * writes only to a temporary file.
4. End-to-End
    * uses the real LangGraph structure;
    * runs user interaction, approval, and recording;
    * verifies final workflow state and one record per reservation.

The benchmark command can be run with:
``` bash 
python -m parking_chatbot.load_testing
```
The final project installation, setup and running instructions are given in the root README. 
