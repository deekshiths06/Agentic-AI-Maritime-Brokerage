# MARITIME AI — Agentic Maritime Brokerage Platform

An AI-powered maritime freight brokerage platform that helps users analyze shipping routes, estimate freight quotations, evaluate weather risks, and assess shipment sustainability through specialized agents.

## 1. Project Overview

Maritime freight decisions involve several factors, including transportation cost, transit time, route availability, weather conditions, operational risks, and environmental impact.

**MARITIME AI** brings these considerations together in a single web application. Its agent-based architecture separates different responsibilities into specialized modules, allowing the platform to analyze shipment requirements and present relevant information through a user-friendly interface.

### Key objectives

- Simplify maritime freight quotation and route comparison.
- Support informed route-selection decisions.
- Assess weather-related shipping risks.
- Provide shipment and quotation management workflows.
- Evaluate sustainability using transparent, rule-based scoring.
- Provide separate experiences for users and administrators.

## 2. Features

### Route Intelligence

- Analyze available origin–destination combinations.
- Compare routes using available transit-time, distance, and transshipment information.
- Calculate route scores using the application's implemented logic.
- Present alternative routes where available.

### Freight Pricing and Quotations

- Generate freight quotation estimates using the available pricing data and pricing agent.
- Calculate quotation totals using the existing quotation workflow.
- Support quotation review and acceptance.
- Create shipments through the implemented quotation-to-shipment workflow.

> Quotation amounts are application estimates and should not be treated as binding carrier offers unless connected to verified commercial rates.

### Weather Risk Assessment

- Evaluate available weather information for route or shipment analysis.
- Use the existing weather agent and configured data sources.
- Present weather-risk information to help users understand potential shipping disruptions.

Weather information depends on the application's configured data source and its availability. The application should not be described as providing live vessel tracking or guaranteed forecasts unless those capabilities are implemented and verified.

### Sustainability Insights

The Sustainability Insights feature introduces a rule-based assessment of environmental and operational factors associated with a shipping option.

The documented scoring structure allocates up to 100 points across four factors:

| Factor | Weight |
|---|---:|
| Emission intensity | 40 points |
| Speed efficiency | 25 points |
| Port idle/waiting time | 15 points |
| Fuel or technology tier | 20 points |
| **Total** | **100 points** |

The feature is designed to present an overall score, factor-level contributions, and an explanation of the result.

**Important implementation note:** The original `CostSustainabilityAgent` was not present in the repository when this feature was developed. Therefore, the newly created formulas and thresholds must be treated as provisional application-defined rules, not as official IMO Carbon Intensity Indicator (CII) calculations or certified environmental ratings.

The actual score categories, thresholds, input requirements, and response fields must match the current implementation in `backend/app/agents/cost_sustainability_agent.py`.

If required inputs are unavailable, the application should communicate the limitation instead of presenting invented values as actual measurements.

### Shipment Management

The platform supports shipment-related workflows based on the existing implementation, including:

1. Quotation review.
2. Quotation acceptance.
3. Shipment creation.
4. Booking confirmation.
5. Cargo readiness.
6. Origin-port arrival.
7. Vessel departure.
8. In-transit status.
9. Destination-port arrival.
10. Delivery.

The displayed status sequence represents the application's shipment workflow. Real-time GPS or Automatic Identification System (AIS) tracking requires an appropriate external integration.

### User Dashboard

Depending on the implemented modules, users can access their quotations, shipments, shipment details, and relevant route or sustainability information.

Users should only be able to access records permitted by their account and role.

### Admin Dashboard

The administrator interface supports the administrative modules implemented in the application, such as dashboard analytics, feedback management, pricing administration, or other configured management functions.

Administrative data and internal commercial information must remain restricted to authorized administrators.

### Customer-Facing AI Chatbot

The application includes a customer-facing maritime AI chatbot module intended to help users interact with the platform and obtain assistance with maritime-related questions.

Its actual capabilities depend on the configured implementation and integrations.

## 3. Agent-Based Architecture

The backend separates the platform's responsibilities into specialized modules.

| Component | Responsibility |
|---|---|
| Route Agent | Route analysis and alternative comparison |
| Pricing Agent | Freight-price estimation |
| Margin Agent | Commercial margin calculations, subject to access restrictions |
| Quotation Service | Quotation creation and processing |
| Orchestrator | Coordinates relevant agent operations |
| Weather Agent | Weather-risk analysis |
| Customs Agent | Customs-related functionality implemented by the project |
| Sustainability Agent | Rule-based sustainability scoring |
| Executive Dashboard Service | Administrative or executive analytics |

These components should be understood according to their actual source code. Not every agent necessarily uses a large language model; some components may use ordinary Python logic, calculations, datasets, or external APIs.

## 4. Technology Stack

The project uses a web-based architecture with frontend and backend components.

| Layer | Technology |
|---|---|
| Frontend | React |
| UI styling | CSS |
| Frontend build tooling | Vite |
| Backend | Python |
| API framework | FastAPI |
| Data processing | Python and application-specific logic |
| Testing | Python testing tools, including pytest where configured |
| Version control | Git and GitHub |

The database, AI provider, charting library, and external service integrations should be documented according to the packages and configuration actually present in the repository. Do not assume that an integration is configured merely because it is mentioned in this document.

## 5. System Architecture

The application follows this general request flow:

1. A user interacts with the React frontend.
2. The frontend sends a request to the backend API.
3. The backend validates the request and applies authentication and authorization rules.
4. The relevant service or agent processes the request.
5. The backend returns the result in the API response.
6. The frontend displays the result.

For example, a sustainability assessment should follow this flow:

**Frontend → Sustainability API → Sustainability Agent → Validated Score and Factor Breakdown → Frontend Panel**

The agent should remain separate from the presentation layer so that the scoring logic can be tested independently.

## 6. Project Structure

The following is the expected organization of the relevant project files. Verify the exact paths against your current repository.

```text
Agentic-AI-Maritime-Brokerage/
├── backend/
│   ├── main.py
│   ├── app/
│   │   ├── agents/
│   │   │   ├── route_agent.py
│   │   │   ├── pricing_agent.py
│   │   │   ├── margin_agent.py
│   │   │   ├── quotation_service.py
│   │   │   ├── orchestrator.py
│   │   │   ├── weather_agent.py
│   │   │   ├── customs_agent.py
│   │   │   └── cost_sustainability_agent.py
│   │   ├── services/
│   │   │   └── executive_dashboard.py
│   │   ├── data/
│   │   │   └── pricing.csv
│   │   ├── models.py
│   │   ├── routes.csv
│   │   └── weather.csv
│   └── tests/
│       └── test_sustainability_agent.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── App.css
│       └── components/
│           └── SustainabilityInsightsCard.jsx
└── README.md
```

This is a representative structure, not a guarantee that every listed file exists or that no additional files are present.

## 7. Installation and Setup

### Prerequisites

Install the following tools:

- Python version supported by the project's dependencies.
- Node.js and npm.
- Git.
- A code editor such as Visual Studio Code.
- Credentials for any external services required by the application.

### Clone the repository

```bash
git clone https://github.com/deekshiths06/Agentic-AI-Maritime-Brokerage.git
cd Agentic-AI-Maritime-Brokerage
```

### Set up the backend

Open a terminal in the project directory:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install the dependencies using the repository's actual dependency file. If it contains `requirements.txt`, run:

```powershell
python -m pip install -r requirements.txt
```

Start the FastAPI application using the entry point and port configured in the project. For example, if `main.py` exposes the FastAPI object as `app`:

```powershell
python -m uvicorn main:app --reload
```

If the project uses a different module path or port, use the corresponding command instead.

When the server starts successfully, FastAPI commonly exposes interactive API documentation at:

`http://127.0.0.1:8000/docs`

The address and port depend on the actual server configuration.

### Set up the frontend

Open a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite in the terminal.

If the frontend requires a backend URL, configure it using the project's documented environment variables. Never commit secrets or private API keys to GitHub.

## 8. Sustainability API

The sustainability API should accept the inputs required by the current agent, validate them, and return the overall score and factor-level results.

Before documenting an exact endpoint, request schema, or response example, verify the implementation in `backend/main.py` and the sustainability agent.

The API documentation should explain:

- The actual HTTP method and endpoint path.
- Required and optional input fields.
- Units for emissions, speed, and waiting time.
- Validation rules and supported fuel or technology categories.
- The score calculation and category thresholds.
- The response fields and error responses.
- How missing or unavailable inputs are handled.

The endpoint should not invent environmental measurements or imply that provisional scores are official certifications.

## 9. Testing

Run the tests supported by the repository.

If pytest is configured, a typical backend command is:

```powershell
python -m pytest backend/tests -v
```

If running from inside the `backend` directory, the equivalent path may be:

```powershell
python -m pytest tests -v
```

Run the frontend production build:

```powershell
cd frontend
npm run build
```

Tests for the sustainability agent should cover:

- Valid input values.
- Missing or invalid inputs.
- Boundary values for each scoring factor.
- Minimum and maximum score behavior.
- Consistency between the factor breakdown and overall score.
- Correct category selection at configured thresholds.

Also regression-test existing authentication, route analysis, quotations, shipments, and admin permissions.

Only report tests as passing when they have actually completed successfully.

## 10. Security and Reliability

- Keep credentials in environment variables or a secure secrets manager.
- Validate and sanitize API inputs.
- Enforce authentication and role-based authorization on the backend.
- Restrict users to records they are authorized to access.
- Protect administrative functions and internal margin information.
- Avoid logging passwords, tokens, or sensitive personal data.
- Handle API failures and missing data gracefully.
- Avoid presenting simulated shipment status as real-time GPS tracking.
- Keep external API keys and private configuration files out of version control.

## 11. Limitations

The platform's reliability depends on the quality and freshness of its underlying data.

Potential limitations include:

- Pricing results may depend on sample datasets or configured rates.
- Weather analysis depends on the availability and coverage of its data source.
- Route rankings depend on the implemented scoring methodology.
- Sustainability scores depend on input quality and provisional scoring rules.
- Shipment status updates do not necessarily indicate a vessel's live physical location.
- Chatbot functionality depends on its actual model or service configuration.
- Production deployment requires appropriate security, monitoring, and environment configuration.

These limitations should be updated as the project gains verified integrations and testing.

## 12. Future Enhancements

Potential future work includes:

- Integration with verified carrier and freight-rate data.
- More detailed route-risk analysis.
- Verified vessel and port information.
- AIS-based vessel tracking, where appropriate data access is available.
- Better provenance and freshness indicators for external data.
- Validation of sustainability methodology against applicable standards.
- Multilingual support for maritime users.
- Improved automated testing and production monitoring.
- Deployment with secure configuration and observability.

These are possible enhancements, not claims about current functionality.

## 13. Git Workflow

Check the current state before staging changes:

```bash
git status
git diff
```

Stage only the intended files:

```bash
git add README.md
git add <reviewed-file-paths>
```

Commit the changes:

```bash
git commit -m "Update project documentation"
```

Fetch the latest remote information:

```bash
git fetch origin
```

If the local and remote branches have diverged, inspect the history before integrating changes. Do not force-push or rewrite shared history without first preserving and verifying all relevant commits.

Push only after the branch is safely synchronized:

```bash
git push origin main
```

## 14. Project Summary

**MARITIME AI — Agentic Maritime Brokerage Platform** is a web application designed to bring together maritime route analysis, freight quotation estimation, weather-risk assessment, shipment management, and sustainability insights.

Its modular architecture makes it possible to extend the platform with specialized agents and services while keeping the frontend, API, business logic, and data processing responsibilities separate.

The goal is to support more informed maritime decisions through clear information, explainable calculations, and a maintainable application architecture.

---

**Repository:** https://github.com/deekshiths06/Agentic-AI-Maritime-Brokerage

**Project:** MARITIME AI — Agentic Maritime Brokerage Platform

**Documentation status:** Update this README whenever the actual API, dependencies, setup process, features, or scoring methodology changes. Verify all paths and commands against the current repository before publishing.
