import sys
sys.path.insert(0, ".")
from app.agents.route_agent import analyze_route

r = analyze_route("Mumbai", "Kochi", "Perishable", "Fresh Fruits", 2)
print("recommended:", r["recommended_route"])
print("routes:", r["routes"])
print("reasons:", r["reasons"])
print("summary:", r["analysis_summary"])
print("total:", r["total_available_routes"], "mapped:", r["mapped_cargo_type"])
