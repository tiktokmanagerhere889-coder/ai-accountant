# 🧾 AI Accountant

> An AI-powered accounting assistant that automates the full range of daily, monthly, and yearly accounting tasks for a business owner or office admin — built on an Orchestrator + 10 specialist agents + 69 tools architecture.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791?style=flat-square&logo=postgresql)](https://postgresql.org)
[![OpenAI Agents SDK](https://img.shields.io/badge/Agents-OpenAI%20Agents%20SDK-412991?style=flat-square&logo=openai)](https://openai.github.io/openai-agents-python/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20%2B%20Gemini-F55036?style=flat-square)](https://groq.com)
[![Docker](https://img.shields.io/badge/Infra-Docker-2496ED?style=flat-square&logo=docker)](https://docker.com)

---

## 🗺️ System Architecture Diagram

**[→ View Full Workflow Diagram on Lucidchart](https://lucid.app/lucidchart/4fb7df8e-7bbd-4659-994b-14ab77174db9/edit?viewport_loc=-580%2C-136%2C2647%2C1309%2C0_0&invitationId=inv_4f89d381-8178-43e6-bf25-cc70b22a0aeb)**

---

## 📋 Research Paper

The research paper documenting automation mapping for 67 accounting tasks, framework selection, model selection, and system architecture is included in this repository:

**[→ AI_Accountant_Research_Paper.pdf](./AI_Accountant_Research_Paper.pdf)**

---

## 🏗️ What It Does

The system orchestrates **1 Orchestrator + 10 specialist agents** over **69 tools** to handle the complete accounting lifecycle:

| Domain | Agent | Tools |
|--------|-------|-------|
| Daily Operations | Daily Entry Agent | Cash position, transaction recording, receipt processing, bank transactions, petty cash |
| Bookkeeping | Ledger & Master Data Agent | Journal entries, general ledger, AP/AR subledgers, payroll, fixed assets, vendor/customer contacts |
| Period Close | Reconciliation & Banking Agent | Bank reconciliation, accruals, vendor/customer statement matching, cheque clearing, LC/BG tracking |
| Reporting | Month-End Reporting Agent | Unpaid bills, depreciation, amortization, aging reports, budget variance, cash flow forecast |
| Financials | Year-End Close Agent | Trial balance, P&L, balance sheet, cash flow statement, year-end close, retained earnings |
| Cost Accounting | Cost & Budgeting Agent | Breakeven analysis, currency conversion, budget forecast, overhead allocation, revenue recognition |
| Tax | Tax Agent | WHT, EOBI, AMT, sales tax filing, income tax filing, tax planning advisory, list tax filings |
| Compliance | Audit & Regulatory Agent | Anomaly detection, compliance deadlines, internal audit support, statutory registers |
| Advisory | Advisory Agent | Spending analysis, financial ratios, health assessment, cost-cutting recommendations |
| System | System Admin Agent | System health, usage statistics, preferences, scheduled maintenance |

**3 additional features** run as direct backend REST endpoints (no AI): audit trail, user roles/permissions, data backup scheduling.

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 / TypeScript / Tailwind CSS |
| Backend | FastAPI (Python, managed with `uv`) |
| Database | PostgreSQL |
| Data Models | Pydantic v2 |
| Agent Framework | OpenAI Agents SDK — Orchestrator + Agents as Tools pattern |
| Primary LLM | Groq (`meta-llama/llama-4-scout-17b-16e-instruct`) |
| Fallback LLM | Groq (`llama-3.3-70b-versatile`) → Cerebras (`llama3.1-8b`) |
| Containerization | Docker + docker-compose |

---

## 🤖 Agent & Tool Counts

| | Count |
|-|-------|
| Orchestrator agents | 1 |
| Specialist agents | 10 |
| Total tools | 67 |
| Approval-gated tools | 24 |
| Direct-execution tools | 43 |
| Direct backend endpoints (no AI) | 3 |

The **24 approval-gated tools** pause and wait for explicit human confirmation before writing to the database. These cover all irreversible, legally sensitive, or judgement-heavy actions — year-end close, tax filings, bank reconciliation, provisions, related-party flagging, and more.

---

## 🚀 Run Locally

### Prerequisites
- Docker + Docker Compose
- A free [Groq API key](https://console.groq.com) and [Gemini API key](https://aistudio.google.com/app/apikey)

### 1. Clone and configure

```bash
git clone https://github.com/tiktokmanagerhere889-coder/ai-accountant.git
cd ai-accountant
```

Create a `.env` file in the root:

```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_FALLBACK_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-flash-lite-latest
```

### 2. Start all services

```bash
docker-compose up
```

This starts PostgreSQL, the FastAPI backend on `http://localhost:8000`, and the Next.js frontend on `http://localhost:3000`.

### Run without Docker

```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

---

## 📁 Folder Structure

```
ai-accountant/
├── backend/
│   ├── agent_defs/        # Orchestrator + 10 specialist agent definitions
│   ├── tools/             # 67 tool implementations (Pydantic in/out)
│   ├── db/                # PostgreSQL models, migrations, connection
│   ├── tests/             # Unit + E2E test suites (150+ tests)
│   └── main.py            # FastAPI entrypoint
├── frontend/
│   └── src/app/           # Next.js App Router pages and components
├── specs/                 # Feature specs — source of truth for every agent
├── docs/                  # Build process docs and phase notes
├── AI_Accountant_Research_Paper.pdf  # Full research paper
└── docker-compose.yml
```

---

## 🔌 Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | DB + system health check |
| `POST` | `/chat` | Main AI chat — routes to Orchestrator |
| `POST` | `/audit-trail` | Create audit log entry |
| `GET` | `/audit-trail` | List audit trail records |
| `POST` | `/roles` | Create user role |
| `GET` | `/roles` | List all roles |
| `PUT` | `/roles/{id}` | Update a role |
| `POST` | `/backup/trigger` | Trigger a system backup |
| `GET` | `/backup/history` | Backup history log |

---

## 🧪 Tests

```bash
cd backend

# Run all unit tests
python tests/test_ledger_tools_123.py
python tests/test_reconciliation_tools_12.py
python tests/test_month_end_tools_12.py
# ... (150+ tests across all 10 agents)

# Run E2E tests (requires live API keys)
python tests/test_orchestrator_e2e.py
```

---

## 🛡️ Human-in-the-Loop Design

Actions that are irreversible, legally sensitive, or require professional judgement are **approval-gated**: the agent prepares the action, pauses, shows the user exactly what it will do, and only proceeds after explicit approval. This covers:

- Year-end closing (irreversible)
- Tax filing preparation (requires human submission via FBR portal)
- Bank reconciliation (uncertain matches go to review)
- Provisions and contingent liabilities (IAS 37 — legal judgement)
- Related-party transaction flagging
- And 19 more tools

---

## 📄 License

MIT

---

*Built by Hassan Khan as an intern assignment — AI-Powered Accounting and Finance Assistant.*
