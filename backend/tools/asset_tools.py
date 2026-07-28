"""Tool: categorize_fixed_asset — auto-categorize fixed assets and suggest depreciation parameters."""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from db.models import FixedAsset
from tools.schemas import CategorizeFixedAssetInput, CategorizeFixedAssetOutput


# Mapping of keywords to suggested depreciation config
ASSET_CONFIGS = {
    "building": {"useful_life": 40, "method": "straight_line", "residual_pct": Decimal("0.10"), "label": "Building/Property"},
    "property": {"useful_life": 40, "method": "straight_line", "residual_pct": Decimal("0.10"), "label": "Building/Property"},
    "vehicle": {"useful_life": 10, "method": "declining_balance", "residual_pct": Decimal("0.10"), "label": "Vehicle"},
    "car": {"useful_life": 10, "method": "declining_balance", "residual_pct": Decimal("0.10"), "label": "Vehicle"},
    "computer": {"useful_life": 5, "method": "straight_line", "residual_pct": Decimal("0.05"), "label": "Computer/IT"},
    "laptop": {"useful_life": 5, "method": "straight_line", "residual_pct": Decimal("0.05"), "label": "Computer/IT"},
    "it equipment": {"useful_life": 5, "method": "straight_line", "residual_pct": Decimal("0.05"), "label": "Computer/IT"},
    "furniture": {"useful_life": 10, "method": "straight_line", "residual_pct": Decimal("0.10"), "label": "Furniture"},
    "machinery": {"useful_life": 15, "method": "declining_balance", "residual_pct": Decimal("0.10"), "label": "Machinery"},
    "equipment": {"useful_life": 15, "method": "declining_balance", "residual_pct": Decimal("0.10"), "label": "Machinery"},
}

DEFAULT_CONFIG = {"useful_life": 5, "method": "straight_line", "residual_pct": Decimal("0.05"), "label": "Other"}


def _generate_asset_id(db: Session) -> str:
    """Generate a unique asset ID like FA-001."""
    existing = db.query(FixedAsset).count()
    seq = existing + 1
    return "FA-{:03d}".format(seq)


def _detect_category(asset_name: str, asset_category: Optional[str] = None):
    """Detect asset category from explicit category or by matching keywords in asset_name."""
    if asset_category:
        cat_lower = asset_category.lower()
        for key, config in ASSET_CONFIGS.items():
            if key in cat_lower:
                return config["label"], config
        return asset_category, DEFAULT_CONFIG

    name_lower = asset_name.lower()
    for key, config in ASSET_CONFIGS.items():
        if key in name_lower:
            return config["label"], config
    return "Other", DEFAULT_CONFIG


def categorize_fixed_asset(
    input: CategorizeFixedAssetInput,
    db: Session,
) -> CategorizeFixedAssetOutput:
    """Categorize a fixed asset based on name or category and suggest depreciation parameters.

    Saves the asset to the fixed_assets table with status 'pending_approval'.
    Raises ValueError if purchase_cost is less than the computed residual value.
    """
    category_name, config = _detect_category(input.asset_name, input.asset_category)

    residual_value = (input.purchase_cost * config["residual_pct"]).quantize(Decimal("0.01"))

    if input.purchase_cost < residual_value:
        raise ValueError(
            "Purchase cost ({}) is less than calculated residual value ({}). "
            "Please verify the asset cost.".format(input.purchase_cost, residual_value)
        )

    useful_life = config["useful_life"]
    if useful_life < 1:
        useful_life = 1

    asset_id = _generate_asset_id(db)

    asset = FixedAsset(
        asset_id=asset_id,
        asset_name=input.asset_name,
        asset_category=category_name,
        purchase_cost=input.purchase_cost,
        purchase_date=input.purchase_date,
        useful_life_years=useful_life,
        depreciation_method=config["method"],
        residual_value=residual_value,
        current_book_value=input.purchase_cost,
        status="pending_approval",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return CategorizeFixedAssetOutput(
        asset_id=asset.asset_id,
        asset_name=asset.asset_name,
        purchase_cost=asset.purchase_cost,
        suggested_useful_life=asset.useful_life_years,
        suggested_depreciation_method=asset.depreciation_method,
        suggested_residual_value=asset.residual_value,
        needs_approval=True,
        status=asset.status,
    )
