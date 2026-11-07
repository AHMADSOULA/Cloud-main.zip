import os
import time
import requests
from utils.logger import get_logger

log = get_logger("APIDeployer")

REGION = os.getenv("GC_REGION", "europe-west1")
SERVICE_NAME = os.getenv("GC_SERVICE_NAME", "ahmed-vip1")
CONTAINER_IMAGE = os.getenv("GC_CONTAINER_IMAGE", "docker.io/ajndjd2/ahmed-vip1")
CONTAINER_PORT = int(os.getenv("GC_CONTAINER_PORT", "8080"))

def deploy_cloud_run(project_id: str, access_token: str) -> str:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 1. Enable Cloud Run API
    enable_url = f"https://serviceusage.googleapis.com/v1/projects/{project_id}/services/run.googleapis.com:enable"
    try:
        op = requests.post(enable_url, headers=headers, json={}, timeout=60).json()
        if op.get("name"):
            op_name = op["name"]
            deadline = time.time() + 180
            while time.time() < deadline:
                poll = requests.get(f"https://serviceusage.googleapis.com/v1/{op_name}", headers=headers, timeout=30)
                if poll.ok and poll.json().get("done"):
                    if poll.json().get("error"):
                        raise RuntimeError(str(poll.json()["error"]))
                    break
                time.sleep(2)
    except Exception as e:
        log.warning(f"API Enable warning: {e}")

    # 2. Create Cloud Run Service
    parent = f"projects/{project_id}/locations/{REGION}"
    service_url = f"https://run.googleapis.com/v2/{parent}/services/{SERVICE_NAME}"
    payload = {
        "name": f"{parent}/services/{SERVICE_NAME}",
        "ingress": "INGRESS_TRAFFIC_ALL",
        "invokerIamDisabled": True,
        "template": {
            "timeout": "300s",
            "maxInstanceRequestConcurrency": 80,
            "containers": [{
                "name": f"{SERVICE_NAME}-1",
                "image": CONTAINER_IMAGE,
                "ports": [{"name": "http1", "containerPort": CONTAINER_PORT}],
                "resources": {
                    "limits": {"cpu": "1", "memory": "512Mi"}
                }
            }]
        }
    }

    # Create or Update
    response = requests.post(
        f"https://run.googleapis.com/v2/{parent}/services",
        params={"serviceId": SERVICE_NAME},
        headers=headers, json=payload, timeout=60
    )
    
    if response.status_code == 409:
        # Already exists, we update it
        response = requests.patch(
            service_url,
            params={"updateMask": "ingress,invokerIamDisabled,template"},
            headers=headers, json=payload, timeout=60
        )

    if not response.ok:
        raise RuntimeError(f"Cloud Run API Error {response.status_code}: {response.text[:1000]}")

    result = response.json()
    op_name = result.get("name")
    
    # 3. Wait for operation
    if op_name:
        deadline = time.time() + 300
        while time.time() < deadline:
            poll = requests.get(f"https://run.googleapis.com/v2/{op_name}", headers=headers, timeout=30)
            if poll.ok and poll.json().get("done"):
                if poll.json().get("error"):
                    raise RuntimeError(str(poll.json()["error"]))
                break
            time.sleep(3)

    # 4. Get Service URL
    get_response = requests.get(service_url, headers=headers, timeout=45)
    if not get_response.ok:
        raise RuntimeError(f"Failed to get service URL: {get_response.text[:1000]}")
        
    service_data = get_response.json()
    uri = service_data.get("uri")
    if not uri:
        raise RuntimeError("Google did not return a service URL.")
        
    return uri
