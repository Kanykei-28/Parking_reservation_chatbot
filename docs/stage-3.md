## Stage 3: Addition of processing confirmed reservation by using MCP server

The main goal of this stage is to process an approved reservation using MCP and save the confirmed reservation into a text file.
Meaning that an approved reservation is passed to the MCP server and stored automatically.

## Features

At this stage the system supports the following:
* Processes reservations after administrator approval
* Uses an MCP client and MCP server for confirmed reservation processing
* Starts MCP processing immediately after the administrator approves a reservation
* Saves confirmed reservations into a text file
* Stores the reservation in the format: Name | Car Number | Reservation Period | Approval Time
* Does not process pending or rejected reservations
* Prevents duplicate records for the same approval request
* Retries processing through the reservation status flow if the immediate MCP processing fails
* Handles MCP errors without exposing internal implementation details

## System Architecture
``` text
                 User
                   │
                   ▼
           Parking Chatbot
                   │
                   ▼
       Administrator Approval API
                   │
             Administrator
                   │
              ┌────┴────┐
              │         │
           Reject     Approve
                        │
                        ▼
          ApprovedReservationProcessor
                        │
                        ▼
         ConfirmedReservationMCPClient
                        │
                     stdio
                        │
                        ▼
                  MCP Server
                        │
                        ▼
          Confirmed Reservation Storage
                        │
                        ▼
       confirmed_reservations.txt

```
The chatbot and administrator API do not write directly to the confirmed reservation file. Instead, the approved reservation goes through an MCP client, which calls the MCP server. MCP only stores an approved reservation. 

The MCP client uses stdio to connect with the MCP server, which is started as a subprocess. The write_confirmed_reservation tool is made available by the server. This tool receives a structured answer that indicates if the reservation was stored after the client submits the confirmed reservation information.
I used stdio because the MCP server is used internally by the application and does not need its own public HTTP endpoint.


## Structure
* admin/processing.py – prepares an approved reservation for MCP processing
* mcp_client.py – communicates with MCP server
* mcp_server/server.py – exposes MCP tool for writing confirmed reservations
* processing/models.py – defines and validates the confirmed reservation data
* processing/storage.py – handles file storage and duplicate protection
* stage3_admin_server.py – starts the administrator API with confirmed-reservation processing enabled

### Confirmed Reservation Storage
- Confirmed reservations are stored in `data/dynamic/confirmed_reservations.txt`. 
- The approval time comes from the actual administrator decision and is stored with timezone information.
- The approval request UUID is also used internally to identify already processed reservations. It is not added to the required text output.


## Running Stage 3

Stage 3 requires the administrator API and chatbot to run separately.

1. Start the Stage 3 administrator server in the first terminal: 
``` bash
python -m uvicorn parking_chatbot.admin.api:app --reload
```

2. Start the Stage 3 chatbot in another terminal:
``` bash 
python -m parking_chatbot.cli --with-confirmed-processing
```
3. The MCP server itself does not need to be started manually. ConfirmedReservationMCPClient starts it as a subprocess when processing is required. 


After making the reservation in chatbot and approving it, you can find the `data/dynamic/confirmed_reservations.txt` file with the approved reservation infromation. Moreover, the user can check the decision by asking for the reservation status. The limitation here is that CLI does not automatically print the new status while it is waiting for user input. Automatic update of the complete workflow is left for Stage 4, where the components will be orchestrated using LangGraph.



