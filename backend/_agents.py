import sys, json
sys.path.insert(0, ".")
from app.agents.weather_agent import analyze_weather
from app.agents.customs_agent import analyze_customs
from app.agents.pricing_agent import calculate_pricing
from app.agents.margin_agent import calculate_margin

w = analyze_weather(route_id="R00001")
print("WEATHER:", {k: w.get(k) for k in ("available","route_id","weather_risk","risk_reason","wind_speed_knots","wave_height_m","rainfall_mm","visibility_km","storm_risk","weather_condition")})
print("compact keys:", sorted(analyze_weather(route_id="R00001").keys()))

c = analyze_customs(origin="Mumbai", destination="Kochi", cargo_type="Perishable", cargo_subtype="Fresh Fruits", route_id="R00001")
print("CUSTOMS:", {k: c.get(k) for k in ("available","customs_id","route_id","customs_status","compliance_percent","required_controls","satisfied_controls","restricted","compliance_basis","match_type")})
print("missing:", [m.get("label") for m in c.get("missing") or []])

p = calculate_pricing(route_id="R00001", containers=2)
print("PRICING:", p)
m = calculate_margin(cost=p["demand_adjusted_cost_usd"], target_margin_percent=p["target_margin_percent"])
print("MARGIN:", m)
