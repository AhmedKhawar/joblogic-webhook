import requests


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


def addLogBookItem(token, tenant_id, job_id, engineer_id, form_name, form_date, file_url, fileName, asset_id=None):
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
        "TenantId": tenant_id,
        "FileName": fileName
    }

    if asset_id is not None:
        body["AssetId"] = int(asset_id)

    response = requests.post(url, headers=headers, json=body)
    return response.json()
