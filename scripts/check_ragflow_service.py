#!/usr/bin/env python3
"""Check optional RAGFlow service availability for offline evidence scripts."""

from __future__ import annotations

import json

from lib.ragflow_client import RAGFlowClient, RAGFlowConfig


def main() -> None:
    config = RAGFlowConfig.from_env()
    client = RAGFlowClient(config)
    result = {
        "enabled": config.enabled,
        "base_url_configured": bool(config.base_url),
        "dataset_id": config.dataset_id,
        **client.health_check(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
