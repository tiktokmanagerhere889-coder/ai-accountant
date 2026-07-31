"""Tool: categorize_fixed_asset — auto-categorize fixed assets and suggest depreciation parameters.

Depreciation configs (useful life, method, residual %) are resolved from the
`system_config` table (key: `asset_depreciation_configs`) as JSON. The user
controls these values; nothing is hardcoded. If the config is not set, the tool
returns a clear error instead of guessing.
"""
from datetime import date
from decimal import Decimal
from typing import Optional
import json

from sqlalchemy.orm import Session

from db.models import FixedAsset, SystemConfig
from tools.schemas import CategorizeFixedAssetInput, CategorizeFixedAssetOutput

CONFIG_KEY = "asset_depreciation_configs"


def _load_configs(db: Session) -> dict:
    """Load the asset depreciation config JSON from system_config.

    Returns {} if not configured.
    """
    row = db.query(SystemConfig).filter(SystemConfig.config_key == CONFIG_KEY).first()
    if row is None or not row.config_value:
        return {}
    try:
        data = json.loads(row.config_value)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _detect_category(asset_name: str, asset_category: Optional[str], configs: dict):
    """Detect asset category from explicit category or by matching keywords.

    configs: parsed JSON like {"vehicle": {"useful_life": 10, "method": "...",
    "residual_pct": 0.10, "label": "Vehicle"}, ...}
    """
    if not configs:
        raise ValueError(
            "Asset depreciation configs are not set. "
            "Add config_key='asset_depreciation_configs' in system_config as JSON, "
            "e.g. {\"vehicle\": {\"useful_life\": 10, \"method\": \"straight_line\", "
            "\"residual_pct\": 0.10, \"label\": \"Vehicle\"}}"
        )

    search = (asset_category or asset_name).lower()
    for key, cfg in configs.items():
        if key.lower() in search:
            label = cfg.get("label", key)
            return label, cfg
    return None, None


def categorize_fixed_asset(
    input: CategorizeFixedAssetInput,
    db: Session,
) -> CategorizeFixedAssetOutput:
    """Categorize a fixed asset based on name or category and suggest depreciation parameters.

    Config resolved from system_config. Saves the asset to fixed_assets with
    status 'pending_approval'. Raises ValueError if no config or invalid cost.
    """
    configs = _load_configs(db)
    category_name, config = _detect_category(input.asset_name, input.asset_category, configs)

    if config is None:
        raise ValueError(
            f"No depreciation config found for asset '{input.asset_name}' "
            f"(category='{input.asset_category}'). Add a matching entry in "
            "system_config 'asset_depreciation_configs'."
        )

    residual_pct = Decimal(str(config["residual_pct"]))
    residual_value = (input.purchase_cost * residual_pct).quantize(Decimal("0.01"))

    if input.purchase_cost < residual_value:
        raise ValueError(
            "Purchase cost ({}) is less than calculated residual value ({}). "
            "Please verify the asset cost.".format(input.purchase_cost, residual_value)
        )

    asset_id = _generate_asset_id(db)

    asset = FixedAsset(
        asset_id=asset_id,
        asset_name=input.asset_name,
        asset_category=category_name,
        purchase_cost=input.purchase_cost,
        purchase_date=input.purchase_date,
        useful_life_years=int(config["useful_life"]),
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


def _generate_asset_id(db: Session) -> str:
    """Generate a unique asset ID like FA-001."""
    existing = db.query(FixedAsset).count()
    seq = existing + 1
    return "FA-{:03d}".format(seq)
