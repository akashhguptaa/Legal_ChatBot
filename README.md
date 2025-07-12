# Legal ChatBot

This project is a legal chatbot inspired by LawroomAI. It is designed to assist users with legal queries in a conversational manner.

## Getting Started

To run the project locally, follow these steps:

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Set Up the Backend

- Create a virtual environment in the `backend` directory.
- Ensure you have a `.env` file in the `backend` folder with the following variables:
    - `OPENAI_API_KEY`
    - `MONGODB_URI`
- Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Set Up the Frontend

- Navigate to the frontend directory.
- Install the dependencies:

```bash
npm install
```

- Start the frontend server:

```bash
npm run dev
```

### 4. Running the Application

- Run both the backend and frontend servers individually.
- Ensure the backend's base URL is set to `http://localhost:8000`.

---

Feel free to contribute or raise issues for any improvements or bugs.