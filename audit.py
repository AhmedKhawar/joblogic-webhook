import datetime
import json


def log_audit(request_id, step, details=""):
    now = datetime.datetime.now()
    # High precision timestamp up to 4 integer places for fractional seconds (.XXXX)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-2]

    if isinstance(details, (dict, list)):
        details = json.dumps(details)

    # flush=True ensures the logs appear immediately in the Vercel dashboard
    print(f"[{timestamp_str}] [{request_id}] {step}: {details}", flush=True)