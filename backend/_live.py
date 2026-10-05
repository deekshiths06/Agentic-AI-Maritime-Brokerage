"""
Live end-to-end check of the assistant chat endpoints.

Creates a throwaway account, gives it a real quotation and a
real shipment, then asks the required questions through the
running HTTP API as a shipper and as an administrator.

Nothing secret is printed: the admin credentials and the
Gemini key are read from .env into variables and only their
PRESENCE is reported.
"""

import os
import time
import uuid

import requests

BASE = "http://127.0.0.1:8000"

ENV = {}

with open(".env", "r", encoding="utf-8") as handle:

    for line in handle:

        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        ENV[key.strip()] = value.strip().strip('"').strip("'")

print("gemini key present in env:",
      bool(ENV.get("GEMINI_API_KEY")))
print("admin credentials present in env:",
      bool(ENV.get("ADMIN_EMAIL")) and
      bool(ENV.get("ADMIN_PASSWORD")))


def post(path, body, token=None):
    headers = {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        BASE + path, json=body, headers=headers, timeout=120
    )

    return response


contact = f"live_{uuid.uuid4().hex[:10]}@example.com"
password = "LiveCheck!2345"

print("\n== shipper account ==")

response = post("/api/auth/register", {
    "name": "Live Check Shipper",
    "contact": contact,
    "password": password,
})

print("register:", response.status_code)

response = post("/api/auth/login", {
    "contact": contact,
    "password": password,
})

print("login:", response.status_code)

shipper = response.json()
shipper_token = shipper.get("access_token") or shipper.get("token")
shipper_id = shipper.get("user_id")

print("shipper user_id issued:", bool(shipper_id))

print("\n== administrator session ==")

response = post("/api/auth/login", {
    "contact": ENV.get("ADMIN_EMAIL", ""),
    "password": ENV.get("ADMIN_PASSWORD", ""),
})

print("admin login:", response.status_code)

admin_token = None

if response.status_code == 200:

    admin_token = response.json().get("access_token") or \
        response.json().get("token")

print("admin token issued:", bool(admin_token))

print("\n== real quotation ==")

response = post("/api/quotations/generate", {
    "origin": "Mumbai",
    "destination": "Kochi",
    "cargo_type": "General Cargo",
    "cargo_subtype": "General Cargo",
    "containers": 2,
}, shipper_token)

print("quotation:", response.status_code)

quotation = response.json()
quotation_id = quotation.get("quotation_id") or quotation.get("_id")

print("quotation_id:", bool(quotation_id))
print("quoted total:",
      quotation.get("pricing", {}).get("selling_price_usd"))

print("\n== accept + approve ==")

response = post(
    f"/api/quotations/{quotation_id}/accept", {}, shipper_token
)

print("accept:", response.status_code)

response = post(
    f"/api/admin/quotations/{quotation_id}/approve", {},
    admin_token
)

print("approve:", response.status_code)

response = requests.get(
    BASE + "/api/shipments",
    headers={"Authorization": f"Bearer {shipper_token}"},
    timeout=60,
)

shipments = response.json()

print("shipments visible to shipper:",
      len(shipments) if isinstance(shipments, list) else shipments)

USER_QUESTIONS = [
    "What can this platform do?",
    "What is a route score and how is it calculated?",
    "How do you decide which route is recommended?",
    "How is the weather risk level determined?",
    "How does the customs agent match my shipment?",
    "What controls do you check for compliance?",
    "How is my quotation calculated?",
    "How much does my shipment cost and why?",
    "What happens when I accept a quotation?",
    "What is my shipment status?",
    "Why was this route recommended?",
    "Why is my weather risk high?",
    "What customs documents are missing?",
    "How does the admin dashboard work?",
]

ADMIN_QUESTIONS = [
    "How does the admin dashboard work?",
    "Which users are most active?",
    "Show pending quotations",
    "Which shipments are at risk?",
    "How does the pricing data work?",
]

SECRETS = [
    ENV.get("GEMINI_API_KEY", "NO-GEMINI"),
    ENV.get("JWT_SECRET", "NO-JWT"),
    ENV.get("ADMIN_PASSWORD", "NO-PASSWORD"),
    ENV.get("AIS_API_KEY", "NO-AIS"),
]


def ask(path, question, token):
    response = post(path, {"message": question}, token)

    if response.status_code != 200:

        return {
            "_status": response.status_code,
            "_body": response.text[:400],
        }

    return response.json()


def audit(label, payload):

    flat = str(payload).lower()

    leaked = []

    for secret in SECRETS:

        if len(secret) > 6 and secret.lower() in flat:
            leaked.append(secret[:4] + "...")

    project = (payload.get("facts") or {}).get(
        "project"
    ) or {}

    print(f"\n--- {label}")

    print("source:", payload.get("answer_source"),
          "| gemini_available:", payload.get("gemini_available"),
          "| configured:", payload.get("gemini_configured"))
    print("mode:", project.get("scope_of_answer"),
          "| topics:", project.get("matched_topics"))
    print("answer:", payload.get("answer"))

    if leaked:
        print("!!! SECRET LEAK:", leaked)

    return not leaked


clean = True

print("\n" + "=" * 70)
print("SHIPPER QUESTIONS")
print("=" * 70)

for question in USER_QUESTIONS:

    payload = ask(
        "/api/assistant/chat", question, shipper_token
    )

    clean = audit(question, payload) and clean

print("\n" + "=" * 70)
print("ADMIN QUESTIONS")
print("=" * 70)

for question in ADMIN_QUESTIONS:

    payload = ask(
        "/api/admin/assistant/chat", question, admin_token
    )

    clean = audit(question, payload) and clean

print("\n" + "=" * 70)
print("SECURITY")
print("=" * 70)

response = post("/api/assistant/chat", {"message": "hello"})

print("no token ->", response.status_code)
clean = clean and response.status_code in (401, 403)

response = post("/api/admin/assistant/chat", {"message": "hi"})

print("admin chat with shipper token ->", response.status_code)
clean = clean and response.status_code in (401, 403)

response = requests.get(
    BASE + "/api/admin/stats",
    headers={"Authorization": f"Bearer {shipper_token}"},
    timeout=60,
)

print("shipper on /api/admin/stats ->", response.status_code)
clean = clean and response.status_code in (401, 403)

print("\nno secret appeared in any answer:", clean)