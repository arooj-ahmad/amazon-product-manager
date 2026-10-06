"""
Pricing API Routes
"""
from fastapi import APIRouter, HTTPException
from app.schemas.pricing import SinglePricingUpdate, BulkPricingUpdate
from app.services.pricing import pricing_service

router = APIRouter()


@router.get("/countries")
def get_countries():
    """Dropdown ke liye saari countries"""
    try:
        return pricing_service.get_all_countries()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product/{product_id}")
def get_product_pricing(product_id: str):
    """Ek product ki pricing"""
    try:
        return pricing_service.get_pricing_for_product(product_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update")
def update_pricing(data: SinglePricingUpdate):
    """Ek product ka pricing update"""
    try:
        return pricing_service.update_single(
            product_id=data.product_id,
            country_id=data.country_id,
            markup_type=data.markup_type,
            markup_value=data.markup_value,
            tax_rate=data.tax_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-update")
def bulk_update(data: BulkPricingUpdate):
    """Bulk update - saare products par apply"""
    try:
        return pricing_service.bulk_update(
            country_id=data.country_id,
            markup_type=data.markup_type,
            markup_value=data.markup_value,
            tax_rate=data.tax_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))