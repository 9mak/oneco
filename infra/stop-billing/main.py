"""予算100%到達時にプロジェクトの課金を自動解除するCloud Function。

Budget Pub/Sub通知は閾値に関係なく1日に複数回届くため、
costAmount >= budgetAmount の場合だけ課金解除を実行する。
"""

import base64
import json
import logging

import functions_framework
from googleapiclient import discovery

logging.basicConfig(level=logging.INFO)

PROJECT_ID = "oneco-app"
PROJECT_NAME = f"projects/{PROJECT_ID}"


@functions_framework.cloud_event
def stop_billing(cloud_event) -> None:
    data = json.loads(base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8"))
    cost = data.get("costAmount", 0)
    budget = data.get("budgetAmount", 0)

    if cost < budget:
        logging.info("予算内: cost=%s budget=%s", cost, budget)
        return

    billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
    info = billing.projects().getBillingInfo(name=PROJECT_NAME).execute()
    if not info.get("billingEnabled"):
        logging.info("課金は既に無効: %s", PROJECT_ID)
        return

    billing.projects().updateBillingInfo(
        name=PROJECT_NAME, body={"billingAccountName": ""}
    ).execute()
    logging.warning(
        "予算超過のため課金を解除しました: cost=%s budget=%s project=%s",
        cost,
        budget,
        PROJECT_ID,
    )
