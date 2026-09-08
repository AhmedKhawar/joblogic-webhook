from fastapi import FastAPI, Request
import requests

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
    data = await request.json()
    print(data)

    tenantId = data["tenant_id"]
    id = data["data"]["id"]

    if data.get("event_type") == 1079:
        form_type = data["data"]["form_type"]
        form_type_1 = "TIVCV"       # Checklist - Vehicles
        form_type_2 = "ACPLACMFSS"   # Air Conditioning Maintenance / F-Gas Service Sheet
        
        if form_type.strip().lower() == form_type_1.strip().lower() or form_type.strip().lower() == form_type_2.strip().lower():
            token = getToken()
            formUrl = "https://uatapi.joblogic.com/api/v1/formslogbook/download"

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            body = {
                "TenantId": tenantId,
                "Id": id
            }

            res = requests.post(formUrl, headers=headers, json=body)
            resV2 = res.json()

            file_source = resV2["Url"]
            job_id = data["data"]["job_id"]
            form_name = data["data"]["form_name"]
            form_date = data["data"]["date_created"]
            engineer_name = data["data"]["engineer"]

            engineer_id = getEngineerId(token, tenantId, engineer_name)

            logbook_res = addLogBookItem(
                token=token,
                tenant_id=tenantId,
                job_id=job_id,
                engineer_id=engineer_id,
                form_name=form_name,
                form_date=form_date,
                file_url=file_source
            )
            return {"status": "success", "message": "Logbook item added successfully", "data": logbook_res}
        else:
            return {"status": "ignored", "message": f"Form type '{form_type}' is not configured for processing"}
    else:
        return {"status": "ignored", "message": f"Unhandled event type: {data.get('event_type')}"}