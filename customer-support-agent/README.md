# 📦 Customer Support Agent

<img src="../assets/support_agent_logo.png" alt="Customer Support Logo" width="120px" align="right" />

An automated shipping support and FAQ answering agent built with the Google **Agent Development Kit (ADK)** and powered by **Gemini 2.5 Flash**.

This agent uses a stateful ReAct workflow. It classifies incoming user queries, routes shipping-related questions (rates, tracking, delivery hours, returns) to a warm, enthusiastic customer service bot, and politely declines irrelevant topics.

---

## 🛠️ Tech Stack & Workflow
* **LLM Engine:** Gemini 2.5 Flash
* **State Management:** ADK Workflow Graph
* **Routing Logic:** Classifier node -> Router node -> FAQ Agent / Decline Node
* **Runtime Environment:** Managed via Python & `uv` package manager

---

## 📂 Project Structure

```
customer-support-agent/
├── app/
│   ├── agent.py               # Stateful workflow, nodes, and LLM agent definitions
│   └── __init__.py            
├── tests/
│   ├── unit/                  # Unit tests for functions and nodes
│   └── integration/           # Integration tests for state routing
├── .env                       # Local environment secrets (API Keys)
├── agents-cli-manifest.yaml   # CLI configuration and metadata
├── pyproject.toml             # Dependencies management
└── uv.lock                    # Dependency lockfile
```

---

## 🚀 How to Run Locally

### 1. Install Dependencies
Make sure you are in this folder (`E:\ai-agent-monorepo\customer-support-agent`) and run:
```powershell
agents-cli install
```

### 2. Set Up API Key
Ensure you have a `.env` file in the folder root containing:
```env
GOOGLE_GENAI_USE_VERTEXAI=False
GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

### 3. Run the Playground
Start the interactive developer web UI:
```powershell
agents-cli playground
```
Then chat with the Support Agent in your browser!

---

## 🧪 Running Tests
We provide a full suite of automated tests. Run them using:
```powershell
uv run pytest tests/unit tests/integration
```

---

## 🌐 Deploying to the Cloud
To deploy your customer support assistant live to Google Cloud Run, execute:
```powershell
gcloud config set project YOUR_PROJECT_ID
agents-cli deploy
```
To set up GitHub Actions CI/CD pipeline:
```powershell
agents-cli scaffold enhance
```
Select **GitHub Actions** and commit the generated workflow files.
