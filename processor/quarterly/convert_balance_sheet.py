from .quarterly_statements_converter_common import process_category
from .audit_balance_sheet import run_quality_check


def main():
    process_category("balance_sheet", run_quality_check)


if __name__ == "__main__":
    main()
