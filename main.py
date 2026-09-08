import datetime
import json
import uuid
from fastapi import FastAPI, Request
import requests

app = FastAPI()

# Standard headers including a browser User-Agent to bypass Azure/Cloudflare 403 blocks
BASE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DEFAULT_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": BASE_USER_AGENT
}


def log_audit(request_id, step, details=""):
    now = datetime.datetime.now()
    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-2]
    
    if isinstance(details, (dict, list)):
        details = json.dumps(details)
        
    print(f"[{timestamp_str}] [{request_id}] {step}: {details}")


def get_auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": BASE_USER_AGENT
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
        if response.status_code != 200:
            print(f"Token Error: Received status {response.status_code} - {response.text}")
            return None
        token_data = response.json()
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print("Token exception:", e)
        return None


def getEngineerId(token, tenant_id, engineer_name):
    url = "https://uatapi.joblogic.com/api/v1/Engineer/GetAll"
    body = {
        "TenantId": tenant_id,
        "SearchTerm": engineer_name
    }
    res = requests.post(url, headers=get_auth_headers(token), json=body, timeout=10)
    if res.status_code != 200:
        raise Exception(f"Failed to fetch engineer (Status {res.status_code}): {res.text}")
        
    res_data = res.json()
    items = res_data.get("Items", [])
    if not items:
        raise Exception(f"No engineer found matching '{engineer_name}'")
    return items[0]["Id"]


def addLogBookItem(token, tenant_id, job_id, engineer_id, form_name, form_date, file_url):
    url = "https://uatapi.joblogic.com/api/v1/formslogbook"
    body = {
        "JobId": int(job_id),
        "EngineerId": int(engineer_id),
        "FormDate": form_date,
        "FormName": form_name,
        "FileSourceType": 3,  # 3 = FileUrl
        "FileUrl": file_url,
        "IsPublic": True,
        "TenantId": tenant_id
    }
    
    response = requests.post(url, headers=get_auth_headers(token), json=body, timeout=10)
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to add logbook item (Status {response.status_code}): {response.text}")
    return response.json()


# ----------------------------------------------------------------------------- #

@app.get("/")
def home():
    return {"message": "hello"}


@app.post("/webhooks/form/visibility")
async def joblogic_webhook(request: Request):
    req_id = str(uuid.uuid4())[:8]
    log_audit(req_id, "Webhook Received", "Started processing webhook")

    try:
        data = await request.json()
    except Exception as e:
        log_audit(req_id, "Error", f"Invalid JSON payload: {str(e)}")
        return {"status": "error", "message": "Malformed JSON payload"}

    log_audit(req_id, "Payload Parsed", {"event_type": data.get("event_type"), "tenant_id": data.get("tenant_id")})

    tenant_id = data.get("tenant_id")
    event_data = data.get("data", {})
    item_id = event_data.get("id")

    if data.get("event_type") == 1079:
        form_type = event_data.get("form_type", "").strip().lower()
        allowed_forms = ["tivcv", "acplacmfss"]
        
        if form_type in allowed_forms:
            log_audit(req_id, "Form Match", f"Form type '{event_data.get('form_type')}' matched")
            
            token = getToken()
            if not token:
                log_audit(req_id, "Error", "Failed to retrieve authentication token")
                return {"status": "error", "message": "Authentication failed"}
            log_audit(req_id, "Token Acquired", "Successfully retrieved API token")
            
            # Step 1: Download Form Link
            form_url = "https://uatapi.joblogic.com/api/v1/formslogbook/download"
            download_body = {
                "TenantId": tenant_id,
                "Id": item_id
            }

            log_audit(req_id, "Form Download Started", f"Fetching URL for Id: {item_id}")
            res = requests.post(form_url, headers=get_auth_headers(token), json=download_body, timeout=15)
            
            if res.status_code != 200:
                log_audit(req_id, "Form Download Failed", f"Status {res.status_code}: {res.text}")
                return {
                    "status": "error", 
                    "message": f"Joblogic returned status {res.status_code}", 
                    "raw_response": res.text
                }

            download_data = res.json()
            file_source = download_data.get("Url")
            log_audit(req_id, "Form Download Complete", f"Got file URL: {file_source}")
            
            # Step 2: Fetch Engineer ID and Insert Logbook Entry
            try:
                job_id = event_data.get("job_id")
                form_name = event_data.get("form_name")
                form_date = event_data.get("date_created")
                engineer_name = event_data.get("engineer")

                log_audit(req_id, "Fetch Engineer", f"Getting ID for engineer: {engineer_name}")
                engineer_id = getEngineerId(token, tenant_id, engineer_name)
                log_audit(req_id, "Engineer ID Retrieved", f"Engineer ID: {engineer_id}")

                log_audit(req_id, "Add Logbook Item Start", f"Adding logbook item for Job: {job_id}")
                logbook_res = addLogBookItem(
                    token=token,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    engineer_id=engineer_id,
                    form_name=form_name,
                    form_date=form_date,
                    file_url=file_source
                )
                log_audit(req_id, "Add Logbook Item Complete", "Logbook item successfully added")
                return {"status": "success", "message": "Logbook item added successfully", "data": logbook_res}
                
            except Exception as e:
                log_audit(req_id, "Processing Error", str(e))
                return {"status": "error", "message": str(e)}

        else:
            log_audit(req_id, "Ignored", f"Form type '{event_data.get('form_type')}' is not configured for processing")
            return {"status": "ignored", "message": f"Form type '{event_data.get('form_type')}' is not configured for processing"}
    else:
        log_audit(req_id, "Ignored", f"Unhandled event type: {data.get('event_type')}")
        return {"status": "ignored", "message": f"Unhandled event type: {data.get('event_type')}"}