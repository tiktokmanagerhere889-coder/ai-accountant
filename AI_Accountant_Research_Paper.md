AI Accountant
Research Paper
A Research Paper on Automating Accounting and Finance Work with an AI Agent
Prepared by
Hassan Khan
Project: AI-Powered Accounting and Finance Assistant

1. Introduction

An accountant or a chartered accountant spends most of the working day on tasks that follow a set
pattern: recording a transaction, checking a balance, closing a month, preparing a statement, or
answering a question about spending. A lot of this work is repetitive and rule based, which makes it a
reasonable candidate for automation. At the same time, a large part of accounting also involves
judgement, legal responsibility, and trust, which means it cannot be handed over to software without a
person checking the result.

This paper looks at the full range of tasks an accountant normally performs, on a daily, weekly, monthly
and yearly basis, and works out which of these tasks can realistically be automated using an AI agent,
which ones can only be partly automated with a human still approving the final step, and which ones
cannot be automated at all. The second half of the paper explains the technical choices made for the
project: which agentic framework was selected to build the AI agent, which AI model is used to power it,
and how the overall system, from the user interface down to the database, is structured.

The project itself is a web application that automates the day-to-day work of an accountant or a
chartered accountant on behalf of its user, who the assignment describes as an office admin or a
business owner. It lets that user manage daily expenses, monthly office expenses, income, and other
financial records through both a normal form-based interface and a chat-style AI assistant. The assistant
can add entries, generate reports such as a profit and loss statement or a balance sheet, run a monthly
audit, and answer questions about the business finances in plain language.

2. Research Methodology

The research for this paper was carried out in three stages. The first stage was building a complete list of
accounting and CA tasks by going through standard bookkeeping and accounting practice, from daily
cash handling up to year-end closing, tax filing, and audit. This list was checked and expanded multiple
times to catch tasks that are easy to miss on a first pass, such as petty cash handling, vendor statement
reconciliation, and statutory registers.

The second stage was mapping each of these tasks to a realistic automation approach. For every task,
the question asked was simple: can an AI agent understand a request in plain language and act on it
directly, can the answer be produced by a fixed formula with the AI only presenting it, does this need an
AI suggestion followed by a human approval, or is this something an AI has no real role in.

The third stage was choosing the technical building blocks, the agentic framework and the AI model, by
comparing the free options available and checking which ones fit the requirement of a natural-language
accounting assistant with a human approval step for sensitive actions.

3. Core Responsibilities of an Accountant or CA, and Automation Mapping

The tasks below are grouped into fourteen categories, covering daily operations, bookkeeping and
ledgers, month-end close, year-end close, financial statements, cost accounting, advanced accounting
topics, banking instruments, tax management, audit, regulatory compliance, budgeting, system-level
administration, and advisory work. Sixty-eight tasks were identified as achievable within the scope of
this project, and each one is mapped below to the way it will actually be automated. Rows belonging to
the same category are grouped together for easier reading.

Four labels are used consistently through the table. AI agent means the assistant can carry out the task
directly from a plain-language request. Backend calculation means the result comes from a fixed formula
or database query, with the AI only presenting the answer in plain language rather than reasoning about
it. AI-assisted, human confirms means the assistant prepares a suggestion or a draft, but a person has to
approve it before it is final, which applies to anything that is legally sensitive, irreversible, or a matter of
judgement. Not automatable means the task depends on a physical action, such as counting stock, that
software cannot do.

The Build Tier column marks whether a task is part of the twelve Core Build features, which get the full
conversational AI treatment end to end, or the remaining fifty-six Simplified Build features, which are
still functional and connected to real data but rely more on backend logic than on open-ended AI
reasoning. This split was made because building sixty-eight features to the same depth was not realistic
in the time available, so the features that best demonstrate the AI agent, and the ones the assignment
explicitly asks for, were prioritized for full depth.

Category | Task | Automation Approach | Build Tier | Note
---------|------|--------------------|-----------|----- 
Daily Operations | Cash position check | Backend calculation | Simplified | Live balance pulled from the database and shown in plain language; no reasoning needed.
Daily Operations | Transaction recording via natural language | AI agent | Core | The user types the entry in plain English, the agent parses it and stores it correctly.
Daily Operations | Invoice and receipt collection and organizing | AI-assisted, human confirms | Simplified | If a photo is uploaded the agent can read the amount and vendor (implemented as `process_receipt_image`), but filing the physical paper is still a human task.
Daily Operations | Bank transaction checking | Backend calculation | Simplified | Straightforward query against stored bank data.
Daily Operations | Bank register entry | Backend calculation | Core | Records a bank statement line (charges, fees, interest) separately from journal entries (implemented as `record_bank_transaction`); supports custom fields per transaction and auto-creates the bank account if it is new.
Daily Operations | Petty cash management | AI agent | Simplified | Small cash entries and replenishment reminders through natural language.
Bookkeeping and Ledgers | Journal entries | AI agent | Core | The agent converts a plain-language transaction into the correct debit and credit entry using fixed accounting rules.
Bookkeeping and Ledgers | General ledger maintenance | Backend calculation | Simplified | Pure aggregation of journal entries, no AI judgement involved.
Bookkeeping and Ledgers | Chart of accounts setup | AI-assisted, human confirms | Simplified | The agent can suggest a starting structure, the owner adjusts it.
Bookkeeping and Ledgers | Accounts payable sub-ledger | Backend calculation | Simplified | A database view with an AI question-answer layer on top.
Bookkeeping and Ledgers | Accounts receivable sub-ledger | Backend calculation | Simplified | Same as above, receivable side.
Bookkeeping and Ledgers | Payroll ledger | Backend calculation | Simplified | Salary minus deductions, a fixed formula.
Bookkeeping and Ledgers | Fixed assets ledger | AI-assisted, human confirms | Simplified | The agent can categorize a newly added asset (implemented as `categorize_fixed_asset`), the record itself is a plain database entry.
Bookkeeping and Ledgers | Vendor and customer master data management | AI agent | Core | Adding a vendor or customer by typing a sentence is one of the clearest natural-language use cases; a single `manage_contact` tool handles both, selected by a `contact_type` parameter, so the two sides are one Core feature.
Month-End Close | Unpaid bills review | AI agent | Simplified | The agent queries the database and returns a clear list.
Month-End Close | Bank reconciliation | AI-assisted, human confirms | Core | The agent attempts to match bank lines with internal records (implemented as `run_bank_reconciliation`); anything uncertain goes to a review queue for approval. The related cheque clearing, letter of credit and bank guarantee, and bank charges tools are listed under Banking Instruments below.
Month-End Close | Accrual entries | AI-assisted, human confirms | Simplified | The agent suggests an accrual based on past patterns, the accountant approves before it posts.
Month-End Close | Prepaid expense adjustment | Backend calculation | Simplified | A simple division of an advance payment across months.
Month-End Close | Depreciation calculation | Backend calculation | Simplified | A fixed formula, no reasoning required.
Month-End Close | Amortization calculation | Backend calculation | Simplified | Same as depreciation, for intangible assets.
Month-End Close | Payroll reconciliation | Backend calculation | Simplified | Matching payroll records against the general ledger.
Month-End Close | Accounts receivable aging report | Backend calculation | Simplified | A grouped query by how overdue each invoice is.
Month-End Close | Accounts payable aging report | Backend calculation | Simplified | Same idea, for vendor bills.
Month-End Close | Variance analysis, budget versus actual | AI agent | Simplified | The agent compares the two numbers (implemented as `analyze_budget_variance`) and explains the likely reason in plain language.
Month-End Close | Loan and debt schedule tracking | Backend calculation | Simplified | An amortization schedule split into principal and interest.
Month-End Close | Cash flow forecasting | AI-assisted, human confirms | Simplified | The agent projects near-term cash needs from historical data, the owner treats it as a guide, not a guarantee.
Month-End Close | Vendor statement reconciliation | AI-assisted, human confirms | Simplified | The agent compares a vendor statement against internal records and flags differences.
Month-End Close | Customer statement reconciliation | AI-assisted, human confirms | Simplified | Same idea, on the receivable side.
Year-End Close | Year-end closing entries | AI-assisted, human confirms | Simplified | This action is irreversible, so a human must click to confirm before books are closed (implemented as `close_fiscal_year`).
Year-End Close | Retained earnings transfer | Backend calculation | Simplified | A one-line formula (implemented as `transfer_retained_earnings`), no reasoning needed.
Year-End Close | Opening and closing balance carry-forward | Backend calculation | Simplified | System logic (implemented as `carry_forward_balances`), not an AI decision.
Year-End Close | Notes to financial statements | AI agent | Simplified | The agent can draft the explanatory note from the data (implemented as `draft_notes_to_financials`), the accountant reviews the wording before it is finalized.
Financial Statements | Trial balance | Backend calculation, AI reviews | Core | Debits must equal credits; the agent flags it if they do not.
Financial Statements | Profit and loss statement | Backend calculation, AI reviews | Core | Revenue minus expenses, the agent explains the result in plain language.
Financial Statements | Balance sheet | Backend calculation, AI reviews | Core | Assets must equal liabilities plus equity; the agent checks this and flags mismatches.
Financial Statements | Cash flow statement | Backend calculation, AI reviews | Core | Sum of operating, investing and financing activity, explained by the agent.
Cost and Management Accounting | Standard costing and variance analysis | AI-assisted, human confirms | Simplified | The owner supplies the standard cost figure, the agent calculates and explains the gap.
Cost and Management Accounting | Cost allocation and overhead apportionment | AI-assisted, human confirms | Simplified | The owner defines the allocation basis, such as per square foot, the agent runs the calculation.
Cost and Management Accounting | Break-even and cost-volume-profit analysis | AI agent | Simplified | A formula (implemented as `calculate_breakeven`) plus a plain-language explanation.
Advanced Accounting Topics | Revenue recognition, percentage of completion | AI-assisted, human confirms | Simplified | The owner provides the completion percentage for a contract, the agent runs the calculation (implemented as `calculate_revenue_recognition`).
Advanced Accounting Topics | Provisions and contingent liabilities | AI-assisted, human confirms | Simplified | This involves legal judgement, so the agent can only flag a possible provision, never decide it alone.
Advanced Accounting Topics | Foreign currency transaction handling | Backend calculation | Simplified | A live exchange-rate lookup feeds a fixed conversion formula (implemented as `convert_foreign_currency`).
Advanced Accounting Topics | Related party transaction flagging | AI-assisted, human confirms | Simplified | The agent flags a transaction that looks connected to an insider, the accountant decides on disclosure.
Banking Instruments | Cheque issuance and clearing tracking | AI agent | Simplified | Tracked through short natural-language updates (implemented as `track_cheque_clearing`).
Banking Instruments | Letter of credit and bank guarantee tracking | AI-assisted, human confirms | Simplified | Tracking can be automated, but issuing the instrument itself is a bank and legal process (implemented as `track_lc_bank_guarantee`).
Banking Instruments | Bank charges reconciliation | Backend calculation | Simplified | Matching bank fee lines against the ledger (implemented as `reconcile_bank_charges`).
Tax Management | Sales tax filing preparation | AI-assisted, human confirms | Simplified | The agent prepares the numbers, a human still submits through the FBR portal since that requires personal credentials.
Tax Management | Income tax filing preparation | AI-assisted, human confirms | Simplified | Same reasoning as sales tax.
Tax Management | Withholding tax calculation | Backend calculation | Simplified | Rule-based but fixed once the rate table is entered.
Tax Management | Tax planning advisory | AI agent | Simplified | A natural fit for conversational guidance (implemented as `get_tax_planning_advice`) based on the stored data.
Tax Management | Sales tax input and output adjustment | AI-assisted, human confirms | Simplified | The calculation is automated, the refund claim itself is filed by a person.
Tax Management | Advance tax and minimum or super tax computation | Backend calculation | Simplified | The rules are complex but still deterministic once coded (implemented as `calculate_advance_minimum_tax`).
Tax Management | Sales tax exemption and zero-rating documentation | AI-assisted, human confirms | Simplified | The agent flags which sales may qualify (implemented as `flag_tax_exemption_zero_rating`), a person confirms before applying it.
Tax Management | EOBI and statutory payroll deductions | Backend calculation | Simplified | Fixed percentage deductions once the rates are entered.
Audit | Internal audit support | AI-assisted, human confirms | Simplified | The agent flags unusual entries (implemented as `support_internal_audit`), final judgement stays with the accountant.
Audit | Anomaly and fraud detection | AI agent | Core | Pattern-based flagging of transactions that look out of place (implemented as `detect_anomaly_transactions`), explained in plain language.
Audit | Audit trail and change log | Backend feature, not an agent tool | Simplified | Timestamp and user-id logging is a database design choice, not a reasoning task, and is exposed through the `/audit-trail` REST endpoints rather than as a registered agent tool.
Audit | Statutory register data maintenance | AI-assisted, human confirms | Simplified | Data is kept up to date automatically (implemented as `maintain_statutory_registers`), legal accuracy is checked by a person.
Regulatory Compliance | Compliance calendar and filing reminders | AI agent | Core | The agent tracks due dates and reminds the owner ahead of time (implemented as `get_compliance_deadlines`).
Budgeting | Budget preparation and forecasting | AI agent | Simplified | The agent drafts a budget from historical spending (implemented as `prepare_budget_forecast`), the owner adjusts it.
System and Administration | Multi-user roles and permissions | Backend feature, not an agent tool | Simplified | Access control is a standard application feature, exposed through the `/roles` REST endpoints rather than as a registered agent tool.
System and Administration | Data backup and retention scheduling | Backend feature, not an agent tool | Simplified | A scheduled backend operation, exposed through the `/backup` REST endpoints; the System Admin agent additionally exposes a bonus `schedule_system_task` tool for scheduling backup, export, and maintenance tasks through natural language.
System and Administration | System health monitoring and usage analytics | AI agent | Simplified | System Admin agent (bonus) checks DB health, agent module status, and usage statistics through natural language (`check_system_status` and `get_usage_statistics`), and manages system configuration through `manage_system_preferences`.
Advisory and Analysis | Spending pattern analysis | AI agent | Core | A direct match to the kind of question the assistant is meant to answer (implemented as `analyze_spending_patterns`), such as spending on utilities in a given month.
Advisory and Analysis | Financial health assessment | AI agent | Simplified | Combines several ratios and trends (implemented as `assess_financial_health`) into a plain-language summary.
Advisory and Analysis | Cost-cutting recommendations | AI agent | Simplified | Suggestions generated from spending patterns already in the system (implemented as `generate_cost_cutting_recommendations`).
Advisory and Analysis | Custom management reporting | AI-assisted, human confirms | Simplified | The owner asks for a custom view in plain language, the agent builds the query (implemented as `generate_custom_report`).
Advisory and Analysis | Financial ratio analysis | AI agent | Core | Standard ratios calculated and explained in plain language (implemented as `calculate_financial_ratios`).

Note: Of the sixty-eight rows in this table, three are backend features rather than registered agent tools. Audit trail and change log is exposed through the `/audit-trail` REST endpoints, multi-user roles and permissions through the `/roles` REST endpoints, and data backup and retention scheduling through the `/backup` REST endpoints. Each remaining row corresponds to one or more registered agent tools; the backend registry holds sixty-eight registered tools in total, including two bonus System Admin tools, `manage_system_preferences` and `schedule_system_task`, that are covered by the System and Administration rows.

3.1 Features Planned for a Later Version

Three tasks came up in the research that are genuine accounting features but were not built into this
first version because of their complexity relative to the time available. They are not abandoned, only
deferred, and each has a condition attached to when it would make sense to add them.

Feature | Why it is planned for later
--------|----------------------------
Lease accounting under IFRS 16 | Requires present-value and annuity calculations for long-term leases, and applies only once the business is holding a lease that this standard covers. It was left out of the first version because of this calculation complexity, and can be added once the business has a lease that needs this treatment.
Investments accounting | Needs a live stock or fund price feed, and only applies once the business holds outside investments such as shares or mutual funds. Planned for later if the business starts investing surplus cash.
Consolidation accounting | Needed only once the business has more than one branch or legal entity and those entities trade with each other. The elimination logic needed to combine their statements correctly is complex enough that it does not belong in a first version built in a few days. Planned for later if the business expands to multiple branches.

3.2 Tasks Considered and Left Out of the Feature List Entirely

During research, five additional tasks came up that are technically part of an accountant's world but do
not have a meaningful automation angle for this kind of application, because they are one-time or
government-only processes that legally require a specific person's login or signature. These are listed
here for completeness, along with the reason each one was left out rather than simply omitted without
explanation.

Task considered and left out | Reason
-----------------------------|-------
NTN and STRN registration | This is a one-time interaction with a government system. There is nothing recurring for an AI assistant to automate here.
Withholding tax certificate generation | This document is generated directly by the FBR system itself. An accounting assistant has no role to play in producing it.
SECP e-filing submission | Submission requires the company's own digital signature and login, which only an authorized officer can hold. The assistant can prepare the numbers and remind about deadlines, but it cannot legally submit on anyone's behalf.
Inventory reconciliation | This depends on physically counting stock in a warehouse or store. There is no natural-language or calculation step here for an AI agent to take over, since the entire task is a physical action performed by a person.
E-invoicing and FBR point-of-sale integration | Real integration needs official FBR sandbox registration and API access, which was not available within the project timeline. Since this depends entirely on an external government process rather than on the application's own logic, it is treated the same way as the other government-controlled tasks above rather than left half-built.

4. Agentic Framework Selection

An agentic framework is the layer of software that turns a language model from something that only
replies with text into something that can actually act. It manages the loop of understanding what the
user wants, deciding which tool or function needs to be called, sending that result back to the model,
and keeping track of the conversation state across multiple steps. Without a framework, all of this would
have to be written by hand, including retry logic and error handling, which is a lot of avoidable work.

Three frameworks were compared for this project.

Framework | How it works | Strengths | Weaknesses
----------|-------------|-----------|----------
LangGraph | Models the agent as a graph of states and steps, built by LangChain. | Native pause-and-resume checkpoints, works with any model provider, very large community. | More setup work to define the graph structure before anything runs.
CrewAI | Organizes multiple agents as a team with defined roles. | Good fit when a task naturally splits into specialist roles, such as researcher and writer. | Less suited to a single continuous accounting workflow that needs approval steps.
OpenAI Agents SDK | A small set of primitives for building an agent and handing tasks between agents. | Native pause, approve, and resume support, very little boilerplate code, and now works with non-OpenAI models through custom model providers. | Slightly less mature ecosystem around this particular pattern compared to LangGraph.

The framework chosen for this project is the OpenAI Agents SDK. Several accounting tasks in this system,
such as bank reconciliation, accrual posting, and year-end closing, need the agent to suggest an action
and then wait for a person to approve it before anything is saved. The OpenAI Agents SDK supports this
pattern natively: a tool can be marked as needing approval, the run pauses when that tool is called, and
it resumes only after the decision is made, with the state saved in between. LangGraph offers a similar
capability through its own checkpointing system and was seriously considered, but it requires more code
to set up the graph structure, and given the very short build window for this project, the smaller amount
of boilerplate code needed by the OpenAI Agents SDK made it the more practical choice. The SDK also no
longer requires an OpenAI model specifically, since it can connect to other providers through custom
model configuration, which matters because this project uses Groq and Gemini rather than an OpenAI
model.

The system uses an Orchestrator plus Agents as Tools pattern: one master Orchestrator agent receives
every user request and routes it to the correct specialist agent by calling it as a tool. Ten specialist
agents handle their respective domains. This pattern keeps each agent small and focused, and means
the Orchestrator never has to know the implementation detail of any individual tool.

5. AI Model Selection

The model providers considered for this project were all free-tier options, since the goal was to build
something that runs without any ongoing cost. The table below compares the main ones looked at.

Provider | Free Limit | Speed | Tool Calling | Note
---------|-----------|-------|-------------|-----
Groq | One thousand requests per day on the higher-quality 70B model (lighter models allow up to 14,400 requests per day). Free tier supports multiple model sizes. | Extremely fast, LPU-based inference. | Supported | Chosen as the primary model provider. Its free-tier limits are documented and predictable, tool-calling support is reliable, and LPU inference makes responses fast enough for a live demo.
Google Gemini | Roughly fifteen requests per minute and one thousand requests per day on the free tier (Flash-Lite model). | Good. | Native and well-documented; OpenAI-compatible endpoint verified. | Chosen as the automatic fallback. If Groq's rate limit is reached, the application switches to Gemini without the user noticing any interruption. Replaced Cerebras, which kept hitting billing/402 errors in production.
Cerebras | About one million tokens per day, no credit card required on the free plan. | Very fast, runs on dedicated inference hardware. | Supported | Initially planned as the fallback, but repeatedly hit billing/402 errors in production, so it was removed entirely in favour of Gemini.
OpenRouter | Around twenty-five free models available through one API key, but capped at fifty requests per day unless a one-time paid credit balance is added. | Varies by model. | Depends on the model chosen. | Considered as the fallback, but the fifty-requests-per-day free cap was judged too tight for a live demo, so Gemini was chosen instead.

Groq is the primary model provider because its free-tier rate limits are predictable, its LPU-based
inference is fast enough for a responsive chat experience, and its tool-calling support is reliable across
the model sizes used in this project. The primary model is meta-llama/llama-4-scout-17b-16e-instruct,
with llama-3.3-70b-versatile as a within-Groq fallback for requests that exceed the primary model's
rate limits. Gemini is configured as the final fallback using gemini-flash-lite-latest: if Groq's daily quota is
exhausted, the application switches over automatically without the user noticing any interruption.
This two-provider, three-model setup was chosen so the work continues without stopping, and so
that no single provider outage or rate-limit event brings the assistant down entirely.

6. System Architecture

The system follows a straightforward request path. A user types a request into the chat interface, or fills
out a form on one of the record-keeping screens. In the chat case, the request goes to the FastAPI
backend, where the Orchestrator agent, built with the OpenAI Agents SDK and powered by Groq as the
primary model, interprets what is being asked. The Orchestrator does not calculate anything itself.
Instead it decides which specialist agent to call, and that specialist agent decides which backend tool to
run — for example a function that generates a profit and loss statement for a given month. That function
runs ordinary Python code against the PostgreSQL database to produce a real, deterministic number.
This number passes through a Pydantic model on its way back, which checks that the shape of the data
is correct, and then the agent turns the result into a plain-language reply for the user. Anything that
needs approval, such as a bank reconciliation match or a year-end closing action, pauses at this point
and waits for the user to approve or reject it before the change is saved.

The reasoning behind separating calculation from reasoning this way is that language models are not
reliable at arithmetic on their own. Every number in this system, whether it is a depreciation figure or a
full balance sheet, comes from ordinary backend code, not from the model guessing. The AI's job is
limited to understanding the request and explaining the result, never to doing the maths itself.

Layer | Choice and Role
------|----------------
Frontend | Next.js with TypeScript, screens for daily expenses, income, ledgers, reports, and the AI chat assistant.
Backend | Python, managed with uv, exposed through a FastAPI application.
Data validation | Pydantic models on every request and response so bad input is rejected before it reaches the database or a formula.
Database | PostgreSQL, storing all transactions, ledgers, and master data.
Agent layer | OpenAI Agents SDK, Orchestrator plus ten specialist agents, connected to Groq as the primary model with Gemini as a fallback.
Containerization | Docker and docker-compose, so the whole stack runs locally with one command.

7. Feature List for Implementation

Based on the research above, sixty-eight features are planned for this version of the project, split into
two build tiers. The twelve Core Build features get the complete conversational treatment, where the
agent understands the request, calls the right tool, and explains the outcome. These twelve were chosen
because they line up directly with what the assignment describes as the heart of the project, and
because together they cover a complete thin slice of the system, from recording a transaction through to
producing a report and answering a question about the data.

1. Recording expenses and income through natural-language chat
2. Automatic journal entry generation from a recorded transaction
3. Adding vendors and customers by typing a plain-language request
4. Generating a trial balance
5. Generating a profit and loss statement
6. Generating a balance sheet
7. Generating a cash flow statement
8. Flagging unusual or out-of-pattern transactions
9. Answering spending questions such as how much was spent on utilities in a given month
10. Simplified bank reconciliation with a human approval step
11. Calculating and explaining financial ratios
12. Tracking compliance deadlines and sending reminders

The remaining fifty-six Simplified Build features, listed in full in section 3, are still connected to real data
in PostgreSQL and still work correctly, but rely more on straightforward backend logic and less on
open-ended language understanding. Three further features, lease accounting, investments accounting,
and consolidation accounting, are documented as a future roadmap rather than built now, for the
reasons explained in section 3.1.

In addition to the sixty-five agent-executable tools, three features are implemented directly in the
backend without any AI involvement: audit trail and change log, multi-user roles and permissions, and
data backup and retention scheduling. These three are standard application features that do not benefit
from language understanding, and are exposed through their own REST endpoints rather than through
the agent chat interface.

8. Conclusion

Going through the full range of accounting work in detail made one thing clear: an AI agent is genuinely
useful for the parts of accounting that involve understanding a request in plain language, retrieving or
calculating data, and explaining a result, but it should not be trusted to make final decisions on anything
irreversible, legally sensitive, or dependent on professional judgement. The project is built around that
boundary, using an AI agent for natural-language entry and explanation, ordinary backend code for every
calculation, and a human approval step wherever the outcome matters. Twenty-four of the sixty-eight
tools require explicit human approval before any data is written, covering all irreversible, legally
sensitive, or judgement-heavy actions. The free-tier model and framework choices made here, Groq as
the primary model provider with Gemini as a fallback, and the OpenAI Agents SDK for orchestration,
were selected specifically to support this approval-based pattern without needing a paid service.

9. References

OpenAI. OpenAI Agents SDK documentation.
LangChain. LangGraph documentation.
CrewAI. CrewAI documentation.
Groq. GroqCloud API documentation and rate limits.
Google. Gemini API documentation, model list, and rate limits.
OpenRouter. OpenRouter API documentation and free model list.
Google. Gemini API documentation and rate limits.
Pydantic. Pydantic documentation for data validation.
FastAPI. FastAPI documentation.
Federal Board of Revenue, Pakistan. IRIS portal and sales tax and income tax filing guidance.
Securities and Exchange Commission of Pakistan. Annual return and statutory filing requirements.

