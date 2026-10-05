import sys
sys.path.insert(0, ".")
from app.agents.pricing_agent import calculate_pricing
from app.agents.margin_agent import calculate_margin
from app.agents.quotation_service import generate_quotation

p = calculate_pricing(route_id="R00001", containers=2, base_freight=2000.0)
print("PRICING:", p)
m = calculate_margin(cost=p["demand_adjusted_cost_usd"], target_margin_percent=p["target_margin_percent"])
print("MARGIN:", m)
q = generate_quotation(origin="Mumbai", destination="Kochi", cargo_type="Perishable", cargo_subtype="Fresh Fruits", containers=2)
print("QUOTE keys:", sorted(q.keys()))
print({k: q.get(k) for k in ("route_id","total_price_usd","status")})
print("pricing:", q.get("pricing"))
print("margin:", q.get("margin"))
