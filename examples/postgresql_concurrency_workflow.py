import os


def main():
    if not os.environ.get("ASCOS_POSTGRES_TEST_URL"):
        print("PostgreSQL integration verification skipped: test URL is not configured.")
        return
    print("PostgreSQL integration is configured; run the optional PostgreSQL test suite.")


if __name__ == "__main__": main()
