from mcp.tool_registry import TOOLS

# Test customer tool
print("Customer Profile:")
print(TOOLS["get_customer_profile"]["function"](customer_id=1))

# Test portfolio tool
print("\nPortfolio:")
print(TOOLS["get_portfolio"]["function"](customer_id=1))

# Test loan tool
print("\nLoans:")
print(TOOLS["check_loan_status"]["function"](customer_id=1))