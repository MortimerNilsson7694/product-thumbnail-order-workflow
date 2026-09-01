from pathlib import Path
import sys

# Make the src-layout package importable when this documented script is run
# directly from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from storefront_workflow import CheckoutRequest, ProductImage, ThumbnailOrderService


def main() -> None:
    request = CheckoutRequest(
        order_id="order-1042",
        customer_email="buyer@example.com",
        product_name="Canvas weekender",
        quantity=2,
        unit_amount_cents=6400,
        images=[
            ProductImage(path=Path("samples/weekender-front.jpg"), alt_text="Front view"),
            ProductImage(path=Path("samples/weekender-side.jpg"), alt_text="Side view"),
        ],
    )
    result = ThumbnailOrderService().checkout(request)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
