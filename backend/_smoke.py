from app.services import project_context as pc

qs = [
    ("What does this project do?", "user"),
    ("Explain the Route Agent.", "user"),
    ("How does the Weather Agent calculate risk?", "user"),
    ("How does the Customs Agent work?", "user"),
    ("How is my quotation calculated?", "user"),
    ("Why was this route recommended?", "user"),
    ("What customs documents are missing?", "user"),
    ("Why is my weather risk high?", "user"),
    ("What is my shipment status?", "user"),
    ("How are the different agents connected?", "user"),
    ("Why are we using FastAPI?", "user"),
    ("Where does Gemini fit into the architecture?", "user"),
    ("How does the frontend communicate with the backend?", "user"),
    ("Explain the admin dashboard.", "admin"),
    ("Give me a summary of active shipments.", "admin"),
    ("Which shipments have customs warnings?", "admin"),
    ("Explain the quotation system.", "admin"),
    ("How does the overall system architecture work?", "admin"),
    ("hello", "user"),
    ("Why was this route recommended and how does the Route Agent work?", "user"),
]

for q, scope in qs:
    c = pc.classify_project_question(q, scope=scope)
    k = pc.build_project_knowledge(q, scope=scope, status_flow=["a","b"])
    print(f"[{scope}] {q}")
    print(f"    mode={c['mode']}  topics={c['topics']}")
    print(f"    answer_len={len(k['deterministic_answer'])}")
