from .currency_converter import CurrencyConverter


def main() -> None:
    app = CurrencyConverter()
    app.run()


if __name__ == "__main__":
    main()
