"""
AI Freshness Classification, Quality Scoring, Spoilage Detection, and Shelf-Life Prediction Service.
Uses Computer Vision (OpenCV, Pillow, NumPy) and Biological Arrhenius Shelf-Life Modeling.
"""

import os
import math
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
from PIL import Image
import numpy as np
import cv2

from app.database import Database
from app.models.inventory_model import FreshnessStatus, FoodCategory, StorageType
from app.config import settings


# Baseline Shelf Life (in days at optimal conditions) and Target Storage Parameters
FOOD_BENCHMARKS = {
    FoodCategory.FRUITS.value: {
        "baseline_shelf_life_days": 14.0,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 4.0,
        "temp_range": (1.0, 7.0),
        "optimal_humidity": 85.0,
        "humidity_range": (80.0, 95.0),
        "q10_factor": 2.2,  # Arrhenius decay acceleration per 10°C rise
    },
    FoodCategory.VEGETABLES.value: {
        "baseline_shelf_life_days": 10.0,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 3.0,
        "temp_range": (1.0, 5.0),
        "optimal_humidity": 90.0,
        "humidity_range": (85.0, 95.0),
        "q10_factor": 2.3,
    },
    FoodCategory.DAIRY.value: {
        "baseline_shelf_life_days": 14.0,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 3.0,
        "temp_range": (1.0, 4.0),
        "optimal_humidity": 50.0,
        "humidity_range": (40.0, 60.0),
        "q10_factor": 2.5,
    },
    FoodCategory.MEAT.value: {
        "baseline_shelf_life_days": 5.0,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 1.0,
        "temp_range": (0.0, 3.0),
        "optimal_humidity": 75.0,
        "humidity_range": (70.0, 85.0),
        "q10_factor": 2.8,
    },
    FoodCategory.FISH.value: {
        "baseline_shelf_life_days": 3.5,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 1.0,
        "temp_range": (0.0, 2.0),
        "optimal_humidity": 80.0,
        "humidity_range": (75.0, 90.0),
        "q10_factor": 3.0,
    },
    FoodCategory.BAKERY.value: {
        "baseline_shelf_life_days": 6.0,
        "optimal_storage_type": StorageType.ROOM_TEMPERATURE.value,
        "optimal_temp_c": 20.0,
        "temp_range": (18.0, 22.0),
        "optimal_humidity": 45.0,
        "humidity_range": (40.0, 55.0),
        "q10_factor": 1.8,
    },
    FoodCategory.GRAINS.value: {
        "baseline_shelf_life_days": 180.0,
        "optimal_storage_type": StorageType.DRY_STORAGE.value,
        "optimal_temp_c": 18.0,
        "temp_range": (15.0, 22.0),
        "optimal_humidity": 40.0,
        "humidity_range": (30.0, 50.0),
        "q10_factor": 1.5,
    },
    FoodCategory.PACKAGED_FOOD.value: {
        "baseline_shelf_life_days": 90.0,
        "optimal_storage_type": StorageType.DRY_STORAGE.value,
        "optimal_temp_c": 20.0,
        "temp_range": (15.0, 25.0),
        "optimal_humidity": 45.0,
        "humidity_range": (35.0, 60.0),
        "q10_factor": 1.4,
    },
    FoodCategory.OTHER.value: {
        "baseline_shelf_life_days": 14.0,
        "optimal_storage_type": StorageType.REFRIGERATED.value,
        "optimal_temp_c": 4.0,
        "temp_range": (1.0, 8.0),
        "optimal_humidity": 65.0,
        "humidity_range": (50.0, 80.0),
        "q10_factor": 2.0,
    },
}


class AIService:
    """Service providing visual freshness classification, defect detection, and shelf-life prediction."""

    @staticmethod
    def process_food_image(image_path: str) -> Dict[str, Any]:
        """
        Analyze food image using computer vision:
        - Checks image validity and extracts RGB/HSV channels
        - Computes oxidation / browning ratio
        - Computes edge entropy & structural surface variation
        """
        full_path = Path(image_path)
        if not full_path.is_absolute():
            # If relative path like /uploads/filename.jpg
            clean_rel = image_path.lstrip("/").replace("uploads/", "")
            full_path = settings.UPLOADS_DIR / clean_rel

        if not full_path.exists():
            return {
                "success": False,
                "error": f"Image file not found at {full_path}",
                "browning_ratio": 0.0,
                "texture_entropy": 0.0,
                "color_uniformity": 1.0,
            }

        try:
            # Read image using OpenCV
            img = cv2.imread(str(full_path))
            if img is None:
                # Try Pillow fallback
                pil_img = Image.open(str(full_path)).convert("RGB")
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            h, w = img.shape[:2]

            # Convert to HSV color space
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Brown / dark decay color mask (Hue 10-30, Saturation 50-255, Value 20-150)
            lower_brown = np.array([10, 50, 20], dtype=np.uint8)
            upper_brown = np.array([30, 255, 150], dtype=np.uint8)
            brown_mask = cv2.inRange(hsv, lower_brown, upper_brown)
            browning_ratio = float(np.count_nonzero(brown_mask)) / float(h * w)

            # Gray scale for surface texture analysis
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            # Normalize texture variance
            texture_score = min(1.0, laplacian_var / 500.0)

            # Color uniformity (variance in saturation channel)
            sat_std = float(np.std(hsv[:, :, 1]))
            color_uniformity = max(0.0, 1.0 - (sat_std / 128.0))

            return {
                "success": True,
                "width": w,
                "height": h,
                "browning_ratio": round(browning_ratio, 4),
                "texture_score": round(texture_score, 4),
                "color_uniformity": round(color_uniformity, 4),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "browning_ratio": 0.0,
                "texture_score": 0.5,
                "color_uniformity": 0.5,
            }

    @classmethod
    def evaluate_freshness(
        cls,
        category: str,
        purchase_date_str: str,
        expiry_date_str: str,
        storage_type: str,
        temperature: Optional[float] = None,
        humidity: Optional[float] = None,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute multi-factor Freshness and Spoilage evaluation combining:
        1. Temporal lifecycle (days elapsed vs days remaining)
        2. Environmental storage conditions (Arrhenius thermal stress)
        3. Visual computer vision indicators (if image provided)
        """
        bench = FOOD_BENCHMARKS.get(category, FOOD_BENCHMARKS[FoodCategory.OTHER.value])

        today = date.today()
        try:
            p_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").date()
        except Exception:
            p_date = today - timedelta(days=2)

        try:
            e_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        except Exception:
            e_date = today + timedelta(days=7)

        total_lifespan = max(1, (e_date - p_date).days)
        elapsed_days = max(0, (today - p_date).days)
        days_remaining = (e_date - today).days

        # Baseline temporal freshness score (100% at purchase -> 0% at expiry)
        temporal_ratio = max(0.0, min(1.0, days_remaining / total_lifespan))
        base_score = temporal_ratio * 100.0

        # Environmental penalty / bonus
        temp_val = temperature if temperature is not None else bench["optimal_temp_c"]
        hum_val = humidity if humidity is not None else bench["optimal_humidity"]

        # Arrhenius temperature penalty
        optimal_t = bench["optimal_temp_c"]
        temp_diff = temp_val - optimal_t
        env_multiplier = 1.0
        defect_indicators = []

        if storage_type != bench["optimal_storage_type"] and storage_type == StorageType.ROOM_TEMPERATURE.value and bench["optimal_storage_type"] == StorageType.REFRIGERATED.value:
            env_multiplier *= 0.55
            defect_indicators.append(f"Suboptimal storage: {category} kept at Room Temperature instead of Refrigeration")

        if temp_diff > 4.0:
            penalty = min(30.0, (temp_diff / 5.0) * 15.0)
            base_score -= penalty
            defect_indicators.append(f"Elevated storage temperature ({temp_val}°C vs optimal {optimal_t}°C)")
        elif temp_val < bench["temp_range"][0] and storage_type != StorageType.FROZEN.value:
            base_score -= 8.0
            defect_indicators.append(f"Chilling injury risk ({temp_val}°C below safe minimum)")

        # Humidity deviation
        opt_h = bench["optimal_humidity"]
        if hum_val < bench["humidity_range"][0]:
            base_score -= 5.0
            defect_indicators.append(f"Low relative humidity ({hum_val}% vs optimal {opt_h}%), moisture loss likely")
        elif hum_val > bench["humidity_range"][1]:
            base_score -= 8.0
            defect_indicators.append(f"Excessive humidity ({hum_val}%), condensation & fungal spore growth risk")

        # Computer vision analysis if image available
        visual_findings = {}
        if image_path:
            cv_res = cls.process_food_image(image_path)
            visual_findings = cv_res
            if cv_res.get("success"):
                browning = cv_res["browning_ratio"]
                if browning > 0.35:
                    base_score -= 35.0
                    defect_indicators.append(f"Severe surface browning/necrosis detected ({round(browning*100, 1)}% surface area)")
                elif browning > 0.15:
                    base_score -= 15.0
                    defect_indicators.append(f"Moderate surface discoloration/oxidation ({round(browning*100, 1)}% area)")

        # If already expired according to date
        if days_remaining < 0:
            base_score = min(base_score, max(5.0, 30.0 - abs(days_remaining) * 5.0))
            defect_indicators.append(f"Passed expiration date by {abs(days_remaining)} day(s)")

        # Bound freshness score to [0.0, 100.0]
        final_freshness_score = round(max(0.0, min(100.0, base_score)), 1)

        # Freshness label
        if final_freshness_score >= 75.0:
            freshness_label = FreshnessStatus.FRESH.value
            quality_grade = "Grade A (Peak Freshness)"
            spoilage_prob = round((100.0 - final_freshness_score) / 100.0 * 0.25, 3)
        elif final_freshness_score >= 45.0:
            freshness_label = FreshnessStatus.MODERATE.value
            quality_grade = "Grade B (Marketable / Consume Soon)"
            spoilage_prob = round(0.25 + (75.0 - final_freshness_score) / 30.0 * 0.45, 3)
        else:
            freshness_label = FreshnessStatus.SPOILED.value
            quality_grade = "Grade C (Spoiled / High Risk)"
            spoilage_prob = round(0.70 + (45.0 - final_freshness_score) / 45.0 * 0.30, 3)

        if not defect_indicators:
            defect_indicators.append("No critical spoilage defects observed; within healthy freshness thresholds")

        # Shelf life prediction calculation
        predicted_shelf_life_days = cls.predict_shelf_life_days(
            category=category,
            freshness_score=final_freshness_score,
            storage_type=storage_type,
            temperature=temp_val,
            humidity=hum_val,
        )

        # Storage recommendations
        recommendations = cls.generate_recommendations(
            category=category,
            freshness_label=freshness_label,
            freshness_score=final_freshness_score,
            storage_type=storage_type,
            temperature=temp_val,
            humidity=hum_val,
            predicted_days=predicted_shelf_life_days,
        )

        return {
            "freshness_score": final_freshness_score,
            "freshness_label": freshness_label,
            "quality_grade": quality_grade,
            "spoilage_probability": min(1.0, max(0.0, spoilage_prob)),
            "predicted_shelf_life_days": predicted_shelf_life_days,
            "defect_indicators": defect_indicators,
            "recommendations": recommendations,
            "visual_metrics": visual_findings,
            "analysis_date": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def predict_shelf_life_days(
        cls,
        category: str,
        freshness_score: float,
        storage_type: str,
        temperature: float,
        humidity: float,
    ) -> float:
        """Calculate predicted remaining shelf life using Arrhenius decay regression."""
        bench = FOOD_BENCHMARKS.get(category, FOOD_BENCHMARKS[FoodCategory.OTHER.value])
        base_days = bench["baseline_shelf_life_days"]

        # Quality coefficient
        quality_ratio = freshness_score / 100.0

        # Arrhenius temperature acceleration
        optimal_t = bench["optimal_temp_c"]
        q10 = bench["q10_factor"]
        temp_delta = max(0.0, temperature - optimal_t)
        thermal_acceleration = math.pow(q10, temp_delta / 10.0)

        # Storage method multiplier
        storage_mult = 1.0
        if storage_type == StorageType.FROZEN.value:
            storage_mult = 6.0
        elif storage_type == StorageType.REFRIGERATED.value:
            storage_mult = 1.0
        elif storage_type == StorageType.ROOM_TEMPERATURE.value:
            storage_mult = 0.35 if bench["optimal_storage_type"] == StorageType.REFRIGERATED.value else 1.0

        estimated_days = (base_days * quality_ratio * storage_mult) / thermal_acceleration
        return round(max(0.1, estimated_days), 1)

    @classmethod
    def generate_recommendations(
        cls,
        category: str,
        freshness_label: str,
        freshness_score: float,
        storage_type: str,
        temperature: float,
        humidity: float,
        predicted_days: float,
    ) -> List[str]:
        """Generate actionable consumption and storage preservation recommendations."""
        bench = FOOD_BENCHMARKS.get(category, FOOD_BENCHMARKS[FoodCategory.OTHER.value])
        recs = []

        if freshness_label == FreshnessStatus.SPOILED.value:
            recs.append("Discard immediately or isolate from inventory to prevent fungal cross-contamination.")
            recs.append("Inspect adjacent batches in the same storage zone for early mold indicators.")
            return recs

        if freshness_label == FreshnessStatus.MODERATE.value:
            recs.append(f"Prioritize consumption or processing within the next {predicted_days} days.")
            recs.append("Consider fast-turnover kitchen use, cooking, or flash freezing to extend preservation.")

        if storage_type != bench["optimal_storage_type"]:
            recs.append(f"Relocate to {bench['optimal_storage_type']} to retard biological enzymatic breakdown.")

        opt_t = bench["optimal_temp_c"]
        if abs(temperature - opt_t) > 2.0:
            recs.append(f"Adjust thermostat closer to target {opt_t}°C (currently {temperature}°C).")

        opt_h = bench["optimal_humidity"]
        if abs(humidity - opt_h) > 15.0:
            if humidity < opt_h:
                recs.append(f"Increase relative humidity toward {opt_h}% (e.g. use sealed crisper or perforated bags).")
            else:
                recs.append(f"Ventilate storage zone to lower humidity from {humidity}% toward safe {opt_h}%.")

        if not recs:
            recs.append("Current storage parameters are optimal. Maintain continuous cold-chain monitoring.")

        return recs

    @classmethod
    def analyze_and_persist(cls, inventory_id: str, user_id: str) -> Dict[str, Any]:
        """
        Analyze an inventory item, record analysis in freshness_records and storage_conditions,
        and update the inventory item document with the calculated status and score.
        """
        if not ObjectId.is_valid(inventory_id):
            raise ValueError("Invalid inventory item ID format")

        inv_col = Database.get_inventory_collection()
        freshness_col = Database.get_freshness_records_collection()
        storage_col = Database.get_storage_conditions_collection()

        item = inv_col.find_one({"_id": ObjectId(inventory_id)})
        if not item:
            raise LookupError("Inventory item not found")

        # Run freshness evaluation
        result = cls.evaluate_freshness(
            category=item.get("category", FoodCategory.OTHER.value),
            purchase_date_str=item.get("purchase_date", date.today().isoformat()),
            expiry_date_str=item.get("expiry_date", (date.today() + timedelta(days=7)).isoformat()),
            storage_type=item.get("storage_type", StorageType.REFRIGERATED.value),
            temperature=item.get("storage_temperature"),
            humidity=item.get("storage_humidity"),
            image_path=item.get("image_url"),
        )

        now = datetime.now(timezone.utc)

        # 1. Insert into freshness_records collection
        freshness_record = {
            "inventory_id": ObjectId(inventory_id),
            "user_id": ObjectId(user_id),
            "food_name": item.get("food_name"),
            "category": item.get("category"),
            "image_url": item.get("image_url"),
            "freshness_score": result["freshness_score"],
            "freshness_label": result["freshness_label"],
            "quality_grade": result["quality_grade"],
            "spoilage_probability": result["spoilage_probability"],
            "predicted_shelf_life": result["predicted_shelf_life_days"],
            "defect_indicators": result["defect_indicators"],
            "recommendations": result["recommendations"],
            "analysis_date": now,
        }
        f_res = freshness_col.insert_one(freshness_record)

        # 2. Record storage condition snapshot
        if item.get("storage_temperature") is not None or item.get("storage_humidity") is not None:
            storage_doc = {
                "inventory_id": ObjectId(inventory_id),
                "user_id": ObjectId(user_id),
                "temperature": item.get("storage_temperature", 4.0),
                "humidity": item.get("storage_humidity", 65.0),
                "storage_location": item.get("location", "Cold Storage"),
                "recorded_at": now,
            }
            storage_col.insert_one(storage_doc)

        # 3. Update parent inventory item
        inv_col.update_one(
            {"_id": ObjectId(inventory_id)},
            {
                "$set": {
                    "freshness_status": result["freshness_label"],
                    "freshness_score": result["freshness_score"],
                    "updated_at": now,
                }
            }
        )

        result["record_id"] = str(f_res.inserted_id)
        result["inventory_id"] = inventory_id
        result["food_name"] = item.get("food_name")
        result["category"] = item.get("category")
        return result
