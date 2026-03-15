from weekly.import_weekly import run
from import_common import (
    abort_with_error,
    get_db_url,
    get_run_config,
    print_run_config,
    wait_for_db,
)
from sqlalchemy import create_engine


def main():
    print("Starting Weekly Importer...")
    engine = create_engine(get_db_url())
    config = get_run_config()
    print_run_config(config)

    try:
        wait_for_db(engine)
        imported_any = run(engine, config)
        if not imported_any:
            print("No weekly data imported.")
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled weekly importer error: {e}", e)


if __name__ == "__main__":
    main()
