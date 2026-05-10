from .quarterly_statements_converter_common import process_category
from .audit_cash_flow import run_quality_check


def main():
    process_category("cash_flow", run_quality_check)


if __name__ == "__main__":
    main()
