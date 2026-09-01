from pathlib import Path

import pytest

from storefront_workflow.product_order import (
    CheckoutRequest,
    InfraiError,
    InfraiImageClient,
    OrderState,
    ProductImage,
    Thumbnail,
    ThumbnailOrderService,
)


class RecordingImageClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def upload(self, image: ProductImage, order_id: str) -> str:
        self.calls.append(("upload", image.path.name))
        return f"source-{image.path.stem}"

    def make_thumbnail(self, image_id: str, order_id: str, index: int) -> Thumbnail:
        self.calls.append(("thumbnail", image_id))
        return Thumbnail(
            source_id=image_id,
            image_id=f"thumb-{index}",
            width=640,
            height=640,
            format="webp",
        )


def test_checkout_prepares_media_before_receipt_and_customer_update() -> None:
    client = RecordingImageClient()
    request = CheckoutRequest(
        order_id="order-7",
        customer_email="ada@example.com",
        product_name="Travel mug",
        quantity=3,
        unit_amount_cents=2500,
        images=[
            ProductImage(path=Path("front.jpg"), alt_text="Front"),
            ProductImage(path=Path("handle.jpg"), alt_text="Handle"),
        ],
    )

    result = ThumbnailOrderService(client).checkout(request)  # type: ignore[arg-type]

    assert client.calls == [
        ("upload", "front.jpg"),
        ("thumbnail", "source-front"),
        ("upload", "handle.jpg"),
        ("thumbnail", "source-handle"),
    ]
    assert result.state is OrderState.CUSTOMER_NOTIFIED
    assert result.receipt.total_cents == 7500
    assert [item.image_id for item in result.thumbnails] == ["thumb-0", "thumb-1"]
    assert result.update.message.endswith("2 responsive thumbnail(s) prepared.")


class FakeResponse:
    status_code = 400
    headers: dict[str, str] = {}

    def json(self) -> dict[str, object]:
        return {
            "ok": False,
            "data": None,
            "error": {"code": "INVALID_ARGUMENT", "message": "width is invalid"},
            "metadata": {},
        }

    def raise_for_status(self) -> None:
        raise AssertionError("status handling ran before envelope handling")


class FakeSession:
    def request(self, **kwargs: object) -> FakeResponse:
        assert kwargs["method"] == "POST"
        return FakeResponse()


def test_business_rejection_is_read_from_envelope_before_status() -> None:
    client = InfraiImageClient(api_key="test-key", session=FakeSession())  # type: ignore[arg-type]

    with pytest.raises(InfraiError) as caught:
        client._request("/v1/image/process", retry_key="order-7:thumbnail:0", json={})

    assert caught.value.code == "INVALID_ARGUMENT"
    assert caught.value.status_code == 400
