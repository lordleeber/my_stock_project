from .quarterly_statements_converter_common import process_category
from .audit_income_statements import run_quality_check


def main():
    process_category("income_statement", run_quality_check)


if __name__ == "__main__":
    main()
