"""TTM-R2 inference service - isolated from main app dependencies.

Runs in separate container with torch~=2.10, transformers~=4.57.
Exposes HTTP endpoint for forecast requests.

This service wraps core/forecasting.py in an HTTP API to isolate the
dependency conflict between tsfm_public (requires torch<2.11) and the
production stack (pins torch==2.11.0).

See docs/adrs/ADR-004-ttm-deployment.md for architecture details.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from core.forecasting import forecast_lap_window
from ingest.schema import Forecast, LapFeatures

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TTM-R2 Forecast Service",
    description="IBM Granite Time Series TTM-R2 inference service for OVERRIDE",
    version="1.0.0"
)


class ForecastRequest(BaseModel):
    """Request payload for forecast endpoint."""
    laps: list[LapFeatures]


class ForecastResponse(BaseModel):
    """Response payload with optional forecast and error details."""
    forecast: Optional[Forecast] = None
    error: Optional[str] = None
    laps_received: int = 0
    eligible: bool = False


@app.get("/health")
async def health():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "service": "ttm-r2",
        "version": "1.0.0"
    }


@app.post("/forecast", response_model=ForecastResponse)
async def predict_forecast(request: ForecastRequest):
    """Run TTM-R2 forecast on provided laps.
    
    Returns:
        ForecastResponse with forecast if successful, None with error otherwise.
        
    The forecast may be None even without error if:
    - Session has < TTM_MIN_LAPS (default 30)
    - Prediction interval width exceeds TTM_MAX_INTERVAL_WIDTH
    - Model checkpoint incompatible with requested context length
    
    This is graceful degradation per FR-3, not a failure.
    """
    try:
        laps_count = len(request.laps)
        logger.info(f"Received forecast request for {laps_count} laps")
        
        # Call core forecasting module
        forecast = forecast_lap_window(request.laps)
        
        eligible = laps_count >= 30  # Simplified eligibility check
        
        if forecast:
            logger.info(
                f"Forecast generated: {len(forecast.point)}-lap horizon, "
                f"model={forecast.model_version}"
            )
        else:
            logger.info(
                f"Forecast returned None (graceful degradation) - "
                f"laps={laps_count}, eligible={eligible}"
            )
        
        return ForecastResponse(
            forecast=forecast,
            laps_received=laps_count,
            eligible=eligible
        )
        
    except Exception as e:
        logger.error(
            f"Forecast failed with exception: {type(e).__name__}: {e}",
            exc_info=True
        )
        return ForecastResponse(
            forecast=None,
            error=f"{type(e).__name__}: {str(e)}",
            laps_received=len(request.laps) if request.laps else 0,
            eligible=False
        )


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting TTM-R2 forecast service on port 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")

# Made with Bob
