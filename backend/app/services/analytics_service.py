"""
Executive Analytics & Reporting Service.
Aggregates real-time inventory, freshness records, and storage condition telemetry from MongoDB.
"""

from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List
from bson import ObjectId
import io
import csv

from app.database import Database
from app.models.user_model import UserRole
from app.models.inventory_model import FreshnessStatus, FoodCategory


class AnalyticsService:

    @classmethod
    def get_executive_metrics(
        cls,
        user: Dict[str, Any],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute comprehensive executive KPI metrics and Chart.js datasets from MongoDB."""
        inv_col = Database.get_inventory_collection()
        freshness_col = Database.get_freshness_records_collection()
        storage_col = Database.get_storage_conditions_collection()

        # Build inventory query
        query: Dict[str, Any] = {}
        if user.get("role") != UserRole.ADMIN.value:
            query["user_id"] = user["_id"]

        if category and category.lower() != "all":
            query["category"] = {"$regex": f"^{category.strip()}$", "$options": "i"}

        if location and location.lower() != "all":
            query["location"] = {"$regex": f"^{location.strip()}$", "$options": "i"}

        if start_date:
            query["created_at"] = query.get("created_at", {})
            query["created_at"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")

        if end_date:
            query["created_at"] = query.get("created_at", {})
            query["created_at"]["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

        # Retrieve inventory items
        items = list(inv_col.find(query))

        today = date.today()
        total_items = len(items)
        total_quantity = round(sum(float(i.get("quantity", 0)) for i in items), 2)

        # Freshness status counts
        fresh_count = 0
        moderate_count = 0
        spoiled_count = 0
        pending_count = 0
        expiring_soon_count = 0
        approaching_expiry_items = []
        waste_quantity = 0.0

        for it in items:
            exp_str = it.get("expiry_date")
            is_exp = False
            days_left = 999
            if exp_str:
                try:
                    exp_d = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_d - today).days
                    if days_left < 0:
                        is_exp = True
                    elif 0 <= days_left <= 3:
                        expiring_soon_count += 1
                        approaching_expiry_items.append({
                            "id": str(it["_id"]),
                            "food_name": it.get("food_name"),
                            "category": it.get("category"),
                            "quantity": it.get("quantity"),
                            "unit": it.get("unit"),
                            "expiry_date": exp_str,
                            "days_remaining": days_left,
                            "location": it.get("location"),
                        })
                except Exception:
                    pass

            status_val = it.get("freshness_status", FreshnessStatus.NOT_ANALYZED.value)
            if is_exp or status_val == FreshnessStatus.SPOILED.value:
                spoiled_count += 1
                waste_quantity += float(it.get("quantity", 0))
            elif status_val == FreshnessStatus.FRESH.value:
                fresh_count += 1
            elif status_val == FreshnessStatus.MODERATE.value:
                moderate_count += 1
            else:
                pending_count += 1

        # Query freshness_records collection for analytical scores
        f_query: Dict[str, Any] = {}
        if user.get("role") != UserRole.ADMIN.value:
            f_query["user_id"] = user["_id"]

        freshness_records = list(freshness_col.find(f_query).sort("analysis_date", -1))
        total_analyses = len(freshness_records)

        scores = [r["freshness_score"] for r in freshness_records if r.get("freshness_score") is not None]
        avg_quality_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        shelf_lives = [r["predicted_shelf_life"] for r in freshness_records if r.get("predicted_shelf_life") is not None]
        avg_shelf_life = round(sum(shelf_lives) / len(shelf_lives), 1) if shelf_lives else 0.0

        # Storage Alerts & Telemetry
        s_query: Dict[str, Any] = {}
        if user.get("role") != UserRole.ADMIN.value:
            s_query["user_id"] = user["_id"]

        storage_records = list(storage_col.find(s_query).sort("recorded_at", 1).limit(50))
        active_storage_alerts = 0
        for it in items:
            st = it.get("storage_type", "")
            temp = it.get("storage_temperature")
            if temp is not None:
                if st == "Refrigerated" and temp > 7.0:
                    active_storage_alerts += 1
                elif st == "Frozen" and temp > -10.0:
                    active_storage_alerts += 1

        # Chart.js Datasets Preparation:
        # A. Freshness Distribution
        freshness_distribution = {
            "labels": ["Fresh (Peak)", "Moderate Freshness", "Spoiled / High Risk", "Awaiting AI Analysis"],
            "data": [fresh_count, moderate_count, spoiled_count, pending_count],
            "colors": ["#10b981", "#f59e0b", "#ef4444", "#94a3b8"],
        }

        # B. Category Analysis
        cat_map: Dict[str, Dict[str, Any]] = {}
        for it in items:
            cat = it.get("category", "Other")
            if cat not in cat_map:
                cat_map[cat] = {"count": 0, "quantity": 0.0, "scores": []}
            cat_map[cat]["count"] += 1
            cat_map[cat]["quantity"] += float(it.get("quantity", 0))
            if it.get("freshness_score") is not None:
                cat_map[cat]["scores"].append(float(it["freshness_score"]))

        cat_labels = list(cat_map.keys())
        cat_quantities = [round(cat_map[c]["quantity"], 1) for c in cat_labels]
        cat_avg_scores = [
            round(sum(cat_map[c]["scores"]) / len(cat_map[c]["scores"]), 1) if cat_map[c]["scores"] else 80.0
            for c in cat_labels
        ]

        category_analysis = {
            "labels": cat_labels,
            "quantities": cat_quantities,
            "average_scores": cat_avg_scores,
        }

        # C. Shelf-Life Distribution Buckets
        bucket_under_2 = sum(1 for it in approaching_expiry_items if it["days_remaining"] < 2)
        bucket_2_5 = sum(1 for it in approaching_expiry_items if 2 <= it["days_remaining"] <= 5)
        bucket_6_10 = sum(1 for it in items if 6 <= (datetime.strptime(it.get("expiry_date", "2099-01-01"), "%Y-%m-%d").date() - today).days <= 10)
        bucket_over_10 = sum(1 for it in items if (datetime.strptime(it.get("expiry_date", "2099-01-01"), "%Y-%m-%d").date() - today).days > 10)

        shelf_life_distribution = {
            "labels": ["Critical (< 2 Days)", "Warning (2-5 Days)", "Stable (6-10 Days)", "Long-Term (10+ Days)"],
            "data": [bucket_under_2, bucket_2_5, bucket_6_10, bucket_over_10],
            "colors": ["#ef4444", "#f59e0b", "#3b82f6", "#10b981"],
        }

        # D. Storage Environmental Telemetry History
        storage_history = {
            "timestamps": [r["recorded_at"].strftime("%m/%d %H:%M") if isinstance(r.get("recorded_at"), datetime) else str(r.get("recorded_at")) for r in storage_records],
            "temperatures": [r.get("temperature", 4.0) for r in storage_records],
            "humidities": [r.get("humidity", 65.0) for r in storage_records],
        }

        # E. Factual Inventory Insights
        insights = []
        if expiring_soon_count > 0:
            insights.append(f"{expiring_soon_count} inventory item(s) are within 3 days of expiration and should be prioritized for consumption or sale.")
        else:
            insights.append("All current perishable items maintain safe expiration margins exceeding 72 hours.")

        if waste_quantity > 0:
            insights.append(f"Recorded {round(waste_quantity, 1)} units of expired or spoiled inventory requiring safe disposal or compost redirection.")

        if cat_map:
            top_category = max(cat_map.items(), key=lambda x: x[1]["quantity"])[0]
            insights.append(f"'{top_category}' represents the largest active inventory category by volume ({round(cat_map[top_category]['quantity'], 1)} units).")

        if active_storage_alerts > 0:
            insights.append(f"{active_storage_alerts} active temperature deviation alert(s) detected. Check cold-chain thermostat settings.")

        return {
            "kpis": {
                "total_items": total_items,
                "total_quantity": total_quantity,
                "total_analyses": total_analyses,
                "fresh_items": fresh_count,
                "moderate_items": moderate_count,
                "spoiled_items": spoiled_count,
                "pending_analysis": pending_count,
                "average_quality_score": avg_quality_score,
                "average_predicted_shelf_life_days": avg_shelf_life,
                "items_expiring_soon": expiring_soon_count,
                "active_storage_alerts": active_storage_alerts,
                "waste_quantity": round(waste_quantity, 2),
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
            "charts": {
                "freshness_distribution": freshness_distribution,
                "category_analysis": category_analysis,
                "shelf_life_distribution": shelf_life_distribution,
                "storage_history": storage_history,
            },
            "approaching_expiry_items": approaching_expiry_items[:10],
            "insights": insights,
        }

    @classmethod
    def generate_inventory_csv(cls, user: Dict[str, Any], category: Optional[str] = None) -> str:
        """Generate formatted CSV string of current inventory records."""
        inv_col = Database.get_inventory_collection()
        query: Dict[str, Any] = {}
        if user.get("role") != UserRole.ADMIN.value:
            query["user_id"] = user["_id"]
        if category and category.lower() != "all":
            query["category"] = category.strip()

        items = list(inv_col.find(query).sort("expiry_date", 1))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Item ID",
            "Food Name",
            "Category",
            "Quantity",
            "Unit",
            "Purchase Date",
            "Expiry Date",
            "Storage Type",
            "Temperature (°C)",
            "Humidity (%)",
            "Location",
            "Batch Number",
            "Freshness Status",
            "Freshness Score (%)",
        ])

        for it in items:
            writer.writerow([
                str(it["_id"]),
                it.get("food_name", ""),
                it.get("category", ""),
                it.get("quantity", ""),
                it.get("unit", ""),
                it.get("purchase_date", ""),
                it.get("expiry_date", ""),
                it.get("storage_type", ""),
                it.get("storage_temperature", ""),
                it.get("storage_humidity", ""),
                it.get("location", ""),
                it.get("batch_number", ""),
                it.get("freshness_status", ""),
                it.get("freshness_score", ""),
            ])

        return output.getvalue()
