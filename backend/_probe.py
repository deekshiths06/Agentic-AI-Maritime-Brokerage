"""Probe: what does the live question actually classify as?"""

import json

from app.services.project_context import (
    classify_project_question,
    build_project_knowledge,
)

QUESTIONS = [
    "What is a route score and how is it calculated?",
    "How do you decide which route is recommended?",
    "How is my quotation calculated?",
    "What happens when I accept a quotation?",
    "How is the weather risk level determined?",
    "What can this platform do?",
]

for question in QUESTIONS:

    result = classify_project_question(
        question, scope="user"
    )

    knowledge = build_project_knowledge(
        question, scope="user", status_flow=["Booking Confirmed","Loaded"]
    )

    print("Q:", question)
    print("  mode:  ", result["mode"])
    print("  topics:", result["topics"])
    print("  sections:", list(knowledge["sections"]))
    print()
