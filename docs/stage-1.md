## Stage 1: Creation of a RAG System and Chatbot

This repository currently contains the implementation of **Stage 1**, which focuses on the RAG system, chatbot, reservation data collection, guardrails, and evaluation.


## Features

So far the chatbot supports following functionality:

- Answers parking-related questions using RAG.
- Stores parking information documentation in a Milvus.
- Collects reservation details through a multi-turn conversation.
- Validates user input during the reservation process.
- Implements guardrails in terms of preveting requests for confidential or internal system information.
- Evaluates RAG and LLM generation.

## System Architecture

```

                User

                  │

                  ▼

          Parking Chatbot

                  │

      ┌───────────┴───────────┐

      │                       │

      ▼                       ▼

 Guardrails             Intent Detection

      │                       │

      └───────────┬───────────┘

                  │

                  ▼

         Reservation Flow

                  │

                  ▼

            RAG Pipeline

                  │

                  ▼

          Milvus Vector DB

                  │

                  ▼

          Azure OpenAI LLM

```

The chatbot first validates the user's request and determines what they want to do. It either starts the reservation or retrieves relevant information from the vector database and generates an answer with LLM.

---

## Project Structure

```

.

├── configs/

├── data/

│   ├── dynamic/

│   ├── evaluation/

│   ├── static/

│   └── vector_store/

├── src/

│   └── parking_chatbot/

│       ├── chatbot/

│       ├── evaluation/

│       └── rag/

└── tests/

```

### Main folders
- **configs/** – LLM (openai) configuration.
- **data/static/** – Dataset containing static information about the parking (FAQ, terms, etc).
- **data/dynamic/** – Dataset containing nformation about the parking places (type, availability, number, etc).
- **data/evaluation/** – Evaluation dataset.
- **data/vector_store/** – Milvus vector database.
- **src/parking_chatbot/chatbot/** – Chatbot, reservation workflow, validation, and guardrails.
- **src/parking_chatbot/rag/** – RAG.
- **src/parking_chatbot/evaluation/** – RAG and LLM evaluation.
- **tests/** – Unit tests.

---

## RAG Pipeline

Sample dataset was created manually. Knowledge base is stored as Markdown documents inside the `data/static`. It contains information about:
- general parking information
- parking location
- working hours
- parking types
- prices
- reservation rules
- and in general frequently asked questions

The RAG piepline uses that dataset, and the pipeline consists of the following steps:
- `loader.py` – loads source Markdown documents
- `splitter.py` – splits documents into chunks
- `embeddings.py` – creates the embedding model
- `vector_store.py` – creates and loads the Milvus vector store
- `retriever.py` – does similarity search
- `generator.py` – builds the prompt and generates the final answer
- `pipeline.py` – connects retrieval and generation into one pipeline

#### Document loading and chunking

Static parking information is in `data/static/`. Loader reads these files and converts them into LangChain `Document` objects. Metadata is attached to each document, including the source filename and document type. The documents are then processed by a recursive text splitter. Metadata from the original document is preserved for every chunk.

#### Embeddings and vector storage

Chunks are converted into dense vectors using Sentence Transformer embedding model. Then they are stored in Milvus Lite. Milvus Lite was selected because it provides vector similarity search while still being lightweight enough to run locally without a separate server.

#### Retrieval

For user query, the system performs vector similarity search against Milvus and selects top 3 relevant chunks. 

#### Answer generation

The generator builds a prompt with:

1. the user's question;
2. the retrieved context;
3. instructions for generating the answer.

LLM is used for answer generation and not as the source of parking information.


---

### Reservation Workflow

Reservation is implemented separately from RAg, and the main components are:
- `Reservation` – stores reservation data
- `ReservationSession` – manages the current multi-turn reservation state
- `reservation_validation.py` – contains validation and normalization logic
- `ParkingChatbot` – coordinates the conversation

#### Multi-turn state

`ParkingChatbot` keeps an active `ReservationSession` while the user is creating a reservation. This helps the chatbot keep track of the reservation process and understand which information it should ask for next.

While the reservation session is active, the user’s messages are treated as answers to the current reservation question. They are not sent to the intent detection system. 

#### Validation
Validation is also done separately in reservation_validation.py. This makes the reservation flow simpler and keeps all validation rules in one place.

The chatbot checks that:
* required fields are not empty;
* extra spaces are removed from the input;
* parking type is converted to lowercase;
* only standard, covered, and ev parking types are accepted;
* dates and times have a valid format;
* dates and times with timezones are not accepted;
* the reservation cannot start in the past;
* a reservation can be made up to 5 days in advance;
* start and end times are within the working hours of 06:00–23:00;
* the end time is later than the start time;
* the reservation is at least 1 hour long;
* the reservation cannot be longer than 15 hours.

Date and time values are also converted to the same format before they are stored. This keeps the reservation data consistent.

### Guardrails

The chatbot also has a simple guardrail mechanism to protect sensitive and internal information. The guardrails are implemented in `chatbot/guardrails.py` and are checked before intent detection or the RAG pipeline.

The guardrails do not simply block messages that contain words such as password or database. They check whether the user is actually asking the chatbot to reveal sensitive information. This is important because some questions containing these words can be completely normal. For example, asking how to restore a forgotten password should not be blocked.

The current guardrails are designed to block requests for:
* internal or hidden prompts
* administrator credentials and passwords
* API keys and access tokens
* environment variables
* database contents or dumps
* personal information about other users

For this stage, rule-based filtering was used instead of LLM because of its simplelicity and latency. 

However, this approach has its limitations. Since the rules are based on words and phrases, they may not recognize every possible way of asking for sensitive information. For a production, I would combine these rules with stronger semantic filtering.

### Evaluation

#### RAG Evaluation 

The RAG system is evaluated using a custom evaluation dataset stored in:

```text
data/evaluation/retrieval_questions.json
```

#### Retrieval evaluation

Retrieval evaluation is done using:

1. **Hit@1**
2. **Hit@K**

The current evaluation uses `K = 3`.
Questions for which `expected_source` is `null` are excluded from retrieval scoring because there is intentionally no relevant source document.

#### Generation evaluation

LLM as a judge was not used here beause most expected answers contain concrete facts such as prices, capacities, times, and reservation rules. Moreover the sample dataset is not that big/difficult. Instead, each evaluation question contains a list of `expected_facts`. The generated answer is normalized and checked for those expected facts using case-insensitive matching.
The final generation metric is the average fact score across the evaluation dataset.


#### Running evaluation

The complete evaluation can be executed with:

```bash
python -m parking_chatbot.evaluate
```

At the current stage, the evaluation dataset contains 18 questions. The latest evaluation produced:

```text
Dataset
-------
Questions: 18

Retrieval
---------
Questions evaluated: 16
Hit@1: 0.62
Hit@3: 0.88

Generation
----------
Questions evaluated: 18
Average fact score: 0.89
```

From the results, we see that the correct source is retrieved within the top three results considerably more often than it is ranked first. This suggests that the current retriever generally finds relevant information but ranking is not the most optimized.

## Installation and Setup

1. Repository cloning

```bash
git clone <repository-url>
cd Epam_parking_reservation_chatbot
```

2. Python environment

```bash
conda create --name parking-chatbot python=3.11 -y
conda activate parking-chatbot
```

3. Project installation

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable installation (`-e`) installs the local `parking_chatbot` package while allowing changes in the source code to be used without reinstalling the package.

4. LLM Configuration

The RAG generator uses the OpenAI-compatible configuration stored in:

```text
configs/openai.json
```

5. Vector database
No separate Milvus server is required because the project uses Milvus Lite.

6. Tests

Running the automated tests:

```bash
pytest
```

Then running the static code checks:

```bash
ruff check .
ruff format --check .
mypy src
```

7. RAG evaluation

```bash
python -m parking_chatbot.evaluate
```

### Running the chatbot

The Stage 1 chatbot without administrator approval can be run directly:

```bash
python -m parking_chatbot.cli
```

For the complete Stage 2 workflow, start the administrator service in one terminal:

```bash
python -m uvicorn parking_chatbot.admin.api:app --reload
```

Then start the chatbot with administrator approval in another terminal:

```bash
ADMIN_APPROVAL_BASE_URL=http://127.0.0.1:8000 \
python -m parking_chatbot.cli --with-admin-approval
```

If `ADMIN_APPROVAL_BASE_URL` is omitted, it defaults to
`http://127.0.0.1:8000`.
