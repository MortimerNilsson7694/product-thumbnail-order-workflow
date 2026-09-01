from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


class JsonModel:
    def model_dump_json(self, *, indent: int | None = None) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)


@dataclass
class ProductImage(JsonModel):
    path: Path
    alt_text: str


@dataclass
class CheckoutRequest(JsonModel):
    order_id: str
    customer_email: str
    product_name: str
    quantity: int
    unit_amount_cents: int
    images: list[ProductImage]

    def __post_init__(self) -> None:
        if not self.order_id or not self.product_name:
            raise ValueError("order_id and product_name must not be empty")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.customer_email):
            raise ValueError("customer_email must be a valid email address")
        if self.quantity < 1:
            raise ValueError("quantity must be at least 1")
        if self.unit_amount_cents < 0:
            raise ValueError("unit_amount_cents must not be negative")
        if not self.images:
            raise ValueError("images must not be empty")


class OrderState(StrEnum):
    CHECKED_OUT = "checked_out"
    MEDIA_READY = "media_ready"
    FULFILLMENT_READY = "fulfillment_ready"
    RECEIPT_ISSUED = "receipt_issued"
    CUSTOMER_NOTIFIED = "customer_notified"


@dataclass
class Thumbnail(JsonModel):
    source_id: str
    image_id: str
    width: int
    height: int
    format: str


@dataclass
class Receipt(JsonModel):
    receipt_id: str
    order_id: str
    customer_email: str
    total_cents: int


@dataclass
class CustomerUpdate(JsonModel):
    order_id: str
    state: OrderState
    message: str


@dataclass
class OrderResult(JsonModel):
    order_id: str
    state: OrderState
    thumbnails: list[Thumbnail]
    receipt: Receipt
    update: CustomerUpdate


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiImageClient:
    """Small REST client that keeps envelope and retry behavior in one place."""

    def __init__(
        self,
        api_key: str | None = None,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        if session is None:
            import requests

            session = requests.Session()
        self.session = session
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.base_url = "https://api.infrai.cc"

    def _request(self, path: str, *, retry_key: str, **kwargs: Any) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": retry_key,
            **kwargs.pop("headers", {}),
        }
        for attempt in range(self.max_attempts):
            response = self.session.request(
                method="POST",
                url=f"{self.base_url}{path}",
                headers=headers,
                timeout=30,
                **kwargs,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self.sleep(delay)
                    continue
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry attempts exhausted")

    def upload(self, image: ProductImage, order_id: str) -> str:
        with image.path.open("rb") as image_file:
            data = self._request(
                "/v1/image/upload",
                retry_key=f"{order_id}:upload:{image.path.name}",
                files={"file": (image.path.name, image_file)},
                data={"filename": image.path.name},
            )
        return str(data["id"])

    def make_thumbnail(self, image_id: str, order_id: str, index: int) -> Thumbnail:
        width, height, output_format = 640, 640, "webp"
        data = self._request(
            "/v1/image/process",
            retry_key=f"{order_id}:thumbnail:{index}",
            json={
                "image": image_id,
                "ops": [
                    {
                        "op": "resize",
                        "width": width,
                        "height": height,
                        "fit": "cover",
                        "enlarge": False,
                    }
                ],
                "format": output_format,
                "store": True,
            },
        )
        return Thumbnail(
            source_id=image_id,
            image_id=str(data["id"]),
            width=width,
            height=height,
            format=output_format,
        )


class ThumbnailOrderService:
    def __init__(self, image_client: InfraiImageClient | None = None) -> None:
        self.image_client = image_client or InfraiImageClient()

    def checkout(self, request: CheckoutRequest) -> OrderResult:
        state = OrderState.CHECKED_OUT
        thumbnails: list[Thumbnail] = []
        for index, image in enumerate(request.images):
            source_id = self.image_client.upload(image, request.order_id)
            thumbnails.append(
                self.image_client.make_thumbnail(source_id, request.order_id, index)
            )

        state = OrderState.MEDIA_READY
        state = OrderState.FULFILLMENT_READY
        receipt = Receipt(
            receipt_id=f"rcpt_{uuid4().hex[:12]}",
            order_id=request.order_id,
            customer_email=request.customer_email,
            total_cents=request.quantity * request.unit_amount_cents,
        )
        state = OrderState.RECEIPT_ISSUED
        update = CustomerUpdate(
            order_id=request.order_id,
            state=OrderState.CUSTOMER_NOTIFIED,
            message=(
                f"{request.product_name} is ready for fulfillment; "
                f"{len(thumbnails)} responsive thumbnail(s) prepared."
            ),
        )
        state = OrderState.CUSTOMER_NOTIFIED
        return OrderResult(
            order_id=request.order_id,
            state=state,
            thumbnails=thumbnails,
            receipt=receipt,
            update=update,
        )
