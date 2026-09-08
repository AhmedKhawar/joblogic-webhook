from fastapi import FastAPI, Request
import requests
import os
import csv
import datetime
import json
import uuid

def log_audit(request_id, step, details=""):
    now = datetime.datetime.now()
    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-2]
    
    if isinstance(details, (dict, list)):
        details = json.dumps(details)
        
    print(f"[{timestamp_str}] [{request_id}] {step}: {details}")



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


def getEngineerId(token, tenant_id, engineer_name):
    url = "https://uatapi.joblogic.com/api/v1/Engineer/GetAll"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "TenantId": tenant_id,
        "SearchTerm": engineer_name
    }
    res = requests.post(url, headers=headers, json=body)
    resV2 = res.json()
    return resV2["Items"][0]["Id"]


def addLogBookItem(token, tenant_id, job_id, engineer_id, form_name, form_date, file_url):
    url = "https://uatapi.joblogic.com/api/v1/formslogbook"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
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
    
    response = requests.post(url, headers=headers, json=body)
    return response.json()


#-------------------------------------------------------------------------------#

@app.get("/")
def home():
    return {"message": "hello"}


@app.post("/webhooks/form/visibility")
async def joblogic_webhook(request: Request):
    req_id = str(uuid.uuid4())[:8]
    log_audit(req_id, "Webhook Received", "Started processing webhook")

    data = await request.json()
    log_audit(req_id, "Payload Parsed", {"event_type": data.get("event_type"), "tenant_id": data.get("tenant_id")})
    print(data)

    tenantId = data["tenant_id"]
    id = data["data"]["id"]

    if data.get("event_type") == 1079:
        form_type = data["data"]["form_type"]
        form_type_1 = "TIVCV"       # Checklist - Vehicles
        form_type_2 = "ACPLACMFSS"   # Air Conditioning Maintenance / F-Gas Service Sheet
        
        if form_type.strip().lower() == form_type_1.strip().lower() or form_type.strip().lower() == form_type_2.strip().lower():
            log_audit(req_id, "Form Match", f"Form type {form_type} matched")
            token = getToken()
            if not token:
                log_audit(req_id, "Error", "Failed to retrieve token")
                return {"status": "error", "message": "Authentication failed"}
            log_audit(req_id, "Token Acquired", "Successfully got API token")
            
            formUrl = "https://uatapi.joblogic.com/api/v1/formslogbook/download"

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            body = {
                "TenantId": tenantId,
                "Id": id
            }

            log_audit(req_id, "Form Download Started", f"Fetching URL for Id: {id}")
            res = requests.post(formUrl, headers=headers, json=body)
            
            # 1. Check if the Joblogic request actually succeeded
            if res.status_code != 200:
                log_audit(req_id, "Form Download Failed", f"Status {res.status_code}: {res.text}")
                return {"status": "error", "message": f"Joblogic returned {res.status_code}", "raw_response": res.text}

            # 2. Safely parse JSON
            resV2 = res.json()
            file_source = resV2.get("Url")
            log_audit(req_id, "Form Download Complete", f"Got file URL: {file_source}")
            
            
            job_id = data["data"]["job_id"]
            form_name = data["data"]["form_name"]
            form_date = data["data"]["date_created"]
            engineer_name = data["data"]["engineer"]

            log_audit(req_id, "Fetch Engineer", f"Getting ID for engineer: {engineer_name}")
            engineer_id = getEngineerId(token, tenantId, engineer_name)
            log_audit(req_id, "Engineer ID Retrieved", f"Engineer ID: {engineer_id}")

            log_audit(req_id, "Add Logbook Item Start", f"Adding logbook item for Job: {job_id}")
            logbook_res = addLogBookItem(
                token=token,
                tenant_id=tenantId,
                job_id=job_id,
                engineer_id=engineer_id,
                form_name=form_name,
                form_date=form_date,
                file_url=file_source
            )
            log_audit(req_id, "Add Logbook Item Complete", "Logbook item successfully added")
            return {"status": "success", "message": "Logbook item added successfully", "data": logbook_res}
        else:
            log_audit(req_id, "Ignored", f"Form type '{form_type}' is not configured for processing")
            return {"status": "ignored", "message": f"Form type '{form_type}' is not configured for processing"}
    else:
        log_audit(req_id, "Ignored", f"Unhandled event type: {data.get('event_type')}")
        return {"status": "ignored", "message": f"Unhandled event type: {data.get('event_type')}"}