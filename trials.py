"""
trials.py — OSCAAR Clinical Trials tab (live proxy to ClinicalTrials.gov v2).

Architecture note (Dave): the route never touches ClinicalTrials.gov directly.
It calls _fetch_studies(), which is the ONLY function that knows where the data
comes from. Today that's a live HTTP call. If you ever add a nightly cache,
you swap the *internals* of _fetch_studies (read from SQLite instead of HTTP)
and this router does not change one line.

Mounted in query_api.py as:
    from trials import router as trials_router
    app.include_router(trials_router)

NOTE ON PREFIX: routes register as /trials/... (NOT /api/trials/...).
Nginx proxies `location /api/` with a trailing-slash proxy_pass that strips the
leading /api before forwarding, so the browser path /api/trials/search arrives
here as /trials/search. Keep this prefix at /trials to match.

DEPLOY REMINDER: this is a .py change -> sudo systemctl restart oscaar-api
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

# Real auth dependency: auth.py defines require_user(request: Request) at line 228,
# which raises on an invalid/absent session. Gating every route with it makes the
# whole tab login-only, same as the Ask screen.
from auth import require_user

router = APIRouter(prefix="/trials", tags=["trials"])

CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Case-sensitive enums straight from the v2 API. Validated before forwarding so a
# typo'd value returns a clean 400 instead of a murky upstream error.
VALID_STATUS = {
    "RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED",
    "ENROLLING_BY_INVITATION", "SUSPENDED", "TERMINATED", "WITHDRAWN", "UNKNOWN",
}
VALID_PHASE = {"EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}


# ---------------------------------------------------------------------------
# THE SEAM. Only this function knows about ClinicalTrials.gov.
# Swap its body for a SQLite read later and nothing above changes.
# ---------------------------------------------------------------------------
async def _fetch_studies(params: dict) -> dict:
    """Make one call to the upstream registry and return raw JSON."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(CTGOV_BASE, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="ClinicalTrials.gov timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"ClinicalTrials.gov returned {e.response.status_code}",
            )
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="ClinicalTrials.gov unreachable")


# ---------------------------------------------------------------------------
# Reshape upstream JSON -> the lean shape the front end renders.
# Defensive everywhere: every array field can be null/empty; dates are messy
# and passed through as-is (no server-side normalization).
# ---------------------------------------------------------------------------
def _summarize(study: dict) -> dict:
    ps = study.get("protocolSection", {}) or {}
    ident = ps.get("identificationModule", {}) or {}
    status = ps.get("statusModule", {}) or {}
    design = ps.get("designModule", {}) or {}
    conds = ps.get("conditionsModule", {}) or {}
    contacts = ps.get("contactsLocationsModule", {}) or {}
    sponsor = ps.get("sponsorCollaboratorsModule", {}) or {}

    nct = ident.get("nctId")
    locations = contacts.get("locations") or []
    loc_summary = [
        {
            "facility": loc.get("facility"),
            "city": loc.get("city"),
            "state": loc.get("state"),
            "country": loc.get("country"),
            "status": loc.get("status"),
        }
        for loc in locations[:25]  # cap; some trials have hundreds of sites
    ]

    return {
        "nctId": nct,
        "url": f"https://clinicaltrials.gov/study/{nct}" if nct else None,
        "title": ident.get("briefTitle"),
        "officialTitle": ident.get("officialTitle"),
        "status": status.get("overallStatus"),
        "phases": design.get("phases") or [],
        "studyType": design.get("studyType"),
        "conditions": conds.get("conditions") or [],
        "leadSponsor": (sponsor.get("leadSponsor") or {}).get("name"),
        "startDate": (status.get("startDateStruct") or {}).get("date"),
        "completionDate": (status.get("completionDateStruct") or {}).get("date"),
        "locationCount": len(locations),
        "locations": loc_summary,
    }


@router.get("/search", dependencies=[Depends(require_user)])
async def search_trials(
    condition: str = Query(..., min_length=2, description="Cancer type / condition"),
    intervention: str | None = Query(None, description="Drug / treatment"),
    status: str | None = Query(None, description="One overallStatus enum value"),
    phase: str | None = Query(None, description="One phase enum value"),
    location: str | None = Query(None, description="US state or country name (query.locn text match)"),
    page_size: int = Query(20, ge=1, le=100),
    page_token: str | None = Query(None, description="Cursor from a previous page"),
):
    """Live search against ClinicalTrials.gov, gated behind OSCAAR login."""
    if status and status not in VALID_STATUS:
        raise HTTPException(400, f"Invalid status. Allowed: {sorted(VALID_STATUS)}")
    if phase and phase not in VALID_PHASE:
        raise HTTPException(400, f"Invalid phase. Allowed: {sorted(VALID_PHASE)}")

    params: dict = {
        "query.cond": condition,
        "pageSize": page_size,
        "countTotal": "true",
        "format": "json",
    }
    if intervention:
        params["query.intr"] = intervention
    if status:
        params["filter.overallStatus"] = status
    if phase:
        # phase lives in aggFilters in v2, not as a top-level filter param.
        params["aggFilters"] = f"phase:{phase[-1] if phase.startswith('PHASE') else phase}"
    if location:
        # query.locn is a text match on site location (state/country name works well).
        params["query.locn"] = location
    if page_token:
        params["pageToken"] = page_token

    data = await _fetch_studies(params)

    studies = [_summarize(s) for s in (data.get("studies") or [])]
    return {
        "totalCount": data.get("totalCount"),
        "nextPageToken": data.get("nextPageToken"),
        "count": len(studies),
        "results": studies,
    }


@router.get("/study/{nct_id}", dependencies=[Depends(require_user)])
async def get_trial(nct_id: str):
    """Full single-trial record, gated. Defensive: NCT may not exist."""
    nct_id = nct_id.strip().upper()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(f"{CTGOV_BASE}/{nct_id}", params={"format": "json"})
            if r.status_code == 404:
                raise HTTPException(404, f"No trial found for {nct_id}")
            r.raise_for_status()
            return r.json()
        except HTTPException:
            raise
        except httpx.HTTPError:
            raise HTTPException(502, "ClinicalTrials.gov unreachable")
