import uuid
from fastapi import FastAPI, Request
import requests
from utils import getEngineerId, addLogBookItem
from audit import log_audit



app = FastAPI()


DEFAULT_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded"
}


def getToken():
    url = "https://uatidentityserver.joblogic.com/connect/token"
    payload = {
        "client_id": "TechnicalSupport-Uat",
        "client_secret": "STEj0bL09ic!Phen",
        "grant_type": "client_credentials",
        "scope": "JL.Api",
    }
    try:
        response = requests.post(url, data=payload, headers=DEFAULT_HEADERS, timeout=10)
        token_data = response.json()
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print("Token error:", e)
        return None





@app.get("/")
def home():
    return {"message": "hello"}


@app.post("/webhooks/form/visibility")
async def joblogic_webhook(request: Request):
    log_audit("Webhook Received", "Started processing webhook")

    try:
        data = await request.json()
    except Exception as e:
        log_audit("Error", f"Failed to parse request body as JSON: {e}")
        return {"status": "error", "message": "Invalid JSON body"}

    log_audit("Payload Parsed", {"event_type": data.get("event_type"), "tenant_id": data.get("tenant_id")})

    tenant_id = data.get("tenant_id")
    event_data = data.get("data", {})
    form_id = event_data.get("id")

    if data.get("event_type") != 1079:
        log_audit("Ignored", f"Unhandled event type: {data.get('event_type')}")
        return {"status": "ignored", "message": f"Unhandled event type: {data.get('event_type')}"}

    form_type = event_data.get("form_type", "")
    allowed_types = {"tivcv", "acplacmfss"}

    if form_type.strip().lower() not in allowed_types:
        log_audit("Ignored", f"Form type '{form_type}' is not configured for processing")
        return {"status": "ignored", "message": f"Form type '{form_type}' is not configured for processing"}

    log_audit("Form Match", f"Form type {form_type} matched")

    # 1. Fetch Auth Token
    token = getToken()
    if not token:
        log_audit("Error", "Authentication failed: unable to retrieve access token")
        return {"status": "error", "message": "Failed to authenticate with Joblogic"}
    log_audit("Token Acquired", "Successfully got API token")

    # 2. Download / Fetch Form URL
    form_url = "https://uatapi.joblogic.com/api/v1/formslogbook/download"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    body = {
        "TenantId": tenant_id,
        "Id": form_id
    }

    log_audit("Form Download Started", f"Fetching URL for Id: {form_id}")
    try:
        download_res = requests.post(form_url, headers=headers, json=body)
    except requests.exceptions.RequestException as e:
        log_audit("Error", f"Form Download network failure: {e}")
        return {"status": "error", "message": "Network error calling download API"}

    if download_res.status_code != 200:
        log_audit("Error", f"Form Download API returned HTTP {download_res.status_code}: {download_res.text}")
        return {"status": "error", "message": f"Form download failed with status {download_res.status_code}"}

    download_json = download_res.json()
    file_source = download_json.get("Url")
    file_name = download_json.get("FileName")

    if not file_source or not file_name:
        log_audit("Error", f"Missing Url or FileName in download response: {download_json}")
        return {"status": "error", "message": "Missing file details from download endpoint"}

    log_audit("Form Download Complete", f"Got file URL: {file_source}")

    # 3. Fetch Engineer ID
    engineer_name = event_data.get("engineer")
    log_audit("Fetch Engineer", f"Getting ID for engineer: {engineer_name}")

    engineer_url = "https://uatapi.joblogic.com/api/v1/Engineer/GetAll"
    engineer_body = {
        "TenantId": tenant_id,
        "SearchTerm": engineer_name
    }

    try:
        engineer_res = requests.post(engineer_url, headers=headers, json=engineer_body)
    except requests.exceptions.RequestException as e:
        log_audit("Error", f"Get Engineer network failure: {e}")
        return {"status": "error", "message": "Network error calling engineer API"}

    if engineer_res.status_code != 200:
        log_audit("Error", f"Engineer API returned HTTP {engineer_res.status_code}: {engineer_res.text}")
        return {"status": "error", "message": f"Engineer lookup failed with status {engineer_res.status_code}"}

    engineer_data = engineer_res.json()
    items = engineer_data.get("Items", [])
    if not items:
        log_audit("Error", f"No engineer found matching '{engineer_name}'")
        return {"status": "error", "message": f"Engineer '{engineer_name}' not found"}

    engineer_id = items[0].get("Id")
    log_audit("Engineer ID Retrieved", f"Engineer ID: {engineer_id}")

    # 4. Add Logbook Item
    job_id = event_data.get("job_id")
    asset_id = event_data.get("asset_id")
    form_name = event_data.get("form_name")
    form_date = event_data.get("date_created")

    log_audit("Add Logbook Item Start", f"Adding logbook item for Job: {job_id}")

    logbook_url = "https://uatapi.joblogic.com/api/v1/formslogbook"
    logbook_body = {
        "JobId": int(job_id),
        "EngineerId": int(engineer_id),
        "FormDate": form_date,
        "FormName": form_name,
        "FileSourceType": 3,
        "FileUrl": file_source,
        "FileName": file_name,
        "IsPublic": True,
        "TenantId": tenant_id
    }

    if asset_id is not None:
        logbook_body["AssetId"] = int(asset_id)

    try:
        logbook_res = requests.post(logbook_url, headers=headers, json=logbook_body)
    except requests.exceptions.RequestException as e:
        log_audit("Error", f"Add Logbook Item network failure: {e}")
        return {"status": "error", "message": "Network error submitting logbook item"}

    if logbook_res.status_code != 200:
        log_audit("Error", f"Add Logbook Item returned HTTP {logbook_res.status_code}: {logbook_res.text}")
        return {"status": "error", "message": f"Logbook creation failed with status {logbook_res.status_code}"}

    log_audit(f"Add Logbook Item Complete", "Logbook item successfully added: {logbook_res}")
    return {"status": "success", "message": "Logbook item added successfully", "data": logbook_res.json()}