TOOLS = [
    {
        "name": "get_customer_profile",
        "description": "Get customer profile",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "get_portfolio",
        "description": "Get portfolio",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "credit_score_tool",
        "description": "Get credit score",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "risk_score_tool",
        "description": "Get risk score",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"}
            },
            "required": ["customer_id"]
        }
    }
]
