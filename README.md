# 🚢 MARITIME AI — Agentic AI for Maritime Freight Pricing and Route Optimization

An AI-powered maritime brokerage platform designed to support freight quotation, route optimization, shipment management, and sustainability assessment through specialized software agents.

## 📌 Project Overview

Maritime freight operations involve multiple decisions, including estimating shipping costs, selecting suitable routes, managing quotations, tracking shipment progress, and evaluating operational efficiency.

**MARITIME AI** brings these activities together in a single web-based platform. It uses a frontend interface, a backend API, data-driven pricing, route analysis, and specialized agents to help users and administrators manage maritime brokerage workflows.

## 🎯 Objectives

- Estimate maritime freight prices using a pricing module.
- Analyze shipping routes between origin and destination ports.
- Support quotation creation and shipment management.
- Calculate estimated arrival times (ETA).
- Evaluate voyage sustainability using predefined scoring rules.
- Provide separate user and administrator workflows.
- Improve visibility into shipment status, operational decisions, and feedback.

## ✨ Key Features

### 1. Freight Price Estimation

The freight pricing module estimates shipping costs using shipment-related information and a pricing model.

The project documentation identifies a **Random Forest model** for freight price prediction. The model's actual input features and output depend on the implemented pricing pipeline.

### 2. Route Optimization

The route optimization module analyzes available connections between ports to identify a suitable route.

The documented approach uses graph-based route processing with NetworkX. Ports can be represented as nodes and shipping connections as edges. Route selection depends on the costs or weights used by the implementation.

### 3. Agent-Based Architecture

The backend contains specialized agents and services for different parts of the maritime workflow.

The repository includes modules for:

- Route analysis
- Freight pricing
- Margin calculation
- Quotation orchestration
- Weather-related information
- Customs-related information
- Cost and sustainability assessment

These modules separate responsibilities and support a structured workflow. The exact degree of autonomous coordination depends on the implemented orchestration logic.

### 4. Cost and Sustainability Assessment

The `CostSustainabilityAgent` evaluates a voyage using four factors:

| Factor | Weight |
|---|---:|
| Emission intensity | 40% |
| Speed-to-efficiency | 25% |
| Port waiting and idle time | 15% |
| Fuel and technology tier | 20% |

The scoring function applies predefined rules to calculate component scores, produces an overall score intended to range from 0 to 100, and assigns a category using configured thresholds.

The result includes the sustainability score, category, rating label, and individual component scores. This provides an explainable, rule-based assessment rather than relying solely on a black-box prediction.

### 5. Estimated Time of Arrival (ETA)

The platform includes ETA-related functionality to support shipment planning and arrival estimates.

An ETA is an estimate and may change because of weather, congestion, vessel speed, or operational delays. It should not be interpreted as proof of real-time GPS or AIS vessel tracking unless those integrations are implemented.

### 6. Shipment and Quotation Workflow

The platform supports maritime brokerage activities involving quotations and shipments.

The intended workflow covers quotation preparation, quotation decisions, shipment creation, booking and shipment-status updates, and delivery progress. The actions available depend on the configured user permissions and current application implementation.

### 7. User and Administrator Functions

The platform separates regular user operations from administrator functions.

**User-side activities**
- Access the user interface.
- Work with quotations and shipment information.
- Review available shipment details.
- Use supported route, pricing, and ETA features.
- Submit feedback where the feedback workflow is enabled.

**Administrator-side activities**
- Access administrative dashboards.
- Review operational information.
- Manage supported shipment and user workflows.
- Review submitted feedback.
- Access administrative analytics where implemented.

Access control should be enforced by the backend as well as the frontend.

## 🧠 Sustainability Scoring Logic

The sustainability agent uses explicit conditional formulas to assign points to different operational factors.

The general scoring process is:

1. Read the relevant voyage and fuel inputs.
2. Calculate the emission-intensity score.
3. Calculate the speed-efficiency score.
4. Calculate the port-waiting score.
5. Assign fuel-category points.
6. Combine the component scores and apply the configured score limits.
7. Assign a sustainability category and rating label.
8. Return the total and component-level results.

This makes the scoring process easier to explain and debug because each component can be inspected separately.

**Note:** The configured CII-style labels are application scoring labels; they should not be treated as official regulatory ratings without validation against the applicable IMO methodology.

## 🏗️ Technology Stack

The project repository and documentation reference the following technologies. Check the current dependency files and configuration before treating every item as part of the final deployed version.

| Component | Technology |
|---|---|
| Frontend | React |
| Language | JavaScript / TypeScript, depending on the module |
| Frontend tooling | Vite |
| UI styling | Tailwind CSS and application styles |
| Backend API | Python and FastAPI |
| Freight pricing | Random Forest model |
| Route analysis | NetworkX / graph-based processing |
| Map integration | Leaflet, where enabled |
| Data storage | Use the database configured in the current repository |
| Data processing | Python and supporting libraries |

## 📂 Project Structure

The repository contains frontend and backend components. The following paths are based on the project structure discussed during development; individual files may change as the application evolves.

```text
Agentic-AI-Maritime-Brokerage/
├── backend/
│   ├── main.py
│   └── app/
│       ├── agents/
│       │   ├── route_agent.py
│       │   ├── pricing_agent.py
│       │   ├── margin_agent.py
│       │   ├── quotation_service.py
│       │   ├── orchestrator.py
│       │   ├── weather_agent.py
│       │   ├── customs_agent.py
│       │   └── cost_sustainability_agent.py
│       ├── data/
│       └── routes.csv
├── frontend/
│   └── src/
│       ├── App.jsx
│       └── App.css
└── README.md
```

This is an illustrative overview, not a complete listing of every file in the repository.

## ⚙️ Getting Started

### Prerequisites

Install the software required by your current project configuration:

- Python
- Node.js and npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/deekshiths06/Agentic-AI-Maritime-Brokerage.git
cd Agentic-AI-Maritime-Brokerage
```

### 2. Set up the backend

Open a terminal in the project directory and enter the backend folder:

```bash
cd backend
python -m venv venv
```

Activate the environment on Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the dependencies using the repository's requirements file, if present:

```bash
pip install -r requirements.txt
```

Start the backend using the application's actual entry point. If `main.py` exposes the FastAPI application as `app`, a typical command is:

```bash
uvicorn main:app --reload
```

If the application entry point is `app.main:app` or uses another module path, use the command appropriate to the current project structure.

### 3. Set up the frontend

Open another terminal and navigate to the frontend folder:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite in the terminal.

**Configuration note:** API URLs, database settings, model paths, environment variables, and other prerequisites must match your actual application configuration. Do not commit passwords, API keys, or `.env` secrets to GitHub.

## 🧪 Testing

Before using or presenting the application, verify the following:

- Backend starts without errors.
- Frontend loads and communicates with the backend.
- Freight price estimation returns valid results.
- Route optimization handles supported ports and missing routes.
- ETA functionality returns valid estimates.
- Sustainability scoring returns a total and component breakdown.
- Quotation and shipment status transitions behave correctly.
- User and administrator permissions are enforced.
- Database operations handle invalid input and missing records.
- Feedback and dashboard features behave as expected.

Only report tests as passing after running them against the version being submitted.

## 🔐 Security Considerations

- Authenticate users before providing protected data.
- Enforce role and ownership checks on the backend.
- Use parameterized database operations.
- Validate incoming request data.
- Store credentials in environment variables or an appropriate secret manager.
- Avoid exposing confidential commercial information, including internal margin calculations, to unauthorized users.
- Do not expose private shipment information across user accounts.

## 🚀 Future Enhancements

Possible future improvements include:

- Integration with reliable real-time vessel AIS data.
- More detailed weather-aware route analysis.
- Expanded fuel and emissions datasets.
- Improved freight pricing validation against actual quotations.
- Better uncertainty estimates for ETA and freight prices.
- Additional maritime analytics and sustainability reports.
- More comprehensive authorization and automated testing.

These are potential enhancements, not claims about existing features.

## 🎓 Project Purpose

MARITIME AI demonstrates how a web application, backend services, data-driven pricing, graph-based route analysis, and specialized agents can be combined to support maritime freight brokerage workflows.

The project aims to make maritime decisions more structured, transparent, and easier to manage.

## 👨‍💻 Repository

GitHub: https://github.com/deekshiths06/Agentic-AI-Maritime-Brokerage.git
