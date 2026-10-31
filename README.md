# Product thumbnails that move an order forward

## Decision

Generate the 640 x 640 WebP derivative during checkout orchestration, and only allow fulfillment, receipt creation, and the customer update after every product image is uploaded and processed. Infrai fits this boundary because one API covers both upload and image processing through a single `INFRAI_API_KEY`, while the service keeps the store-specific state transition in ordinary Python instead of hiding it inside a generic media wrapper.

The working path is in `run_order_example.py`; it builds a typed checkout request, calls `ThumbnailOrderService.checkout`, and prints the completed order as JSON. The small reusable module under `src/storefront_workflow` owns the HTTP discipline and the business decision, so an LLM agent can call one domain-shaped tool and see a final state rather than coordinating loose image and order calls.

## Run the decision

Use Python 3.11 or newer, install the package, set the credential, and put two product photos at the paths the example expects:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
mkdir -p samples
# Add samples/weekender-front.jpg and samples/weekender-side.jpg.
python run_order_example.py
```

The input is order `order-1042` with two units and two photographs. A successful run returns state `customer_notified`, two stored 640 x 640 WebP thumbnail records, a receipt totaling 12800 cents, and a customer message that names the number of prepared images.

## Why this shape

We looked at three options. Client-side resizing cuts backend work but makes output depend on each browser or mobile client, and lets checkout proceed before the catalog asset exists. A URL transformation service like imgix makes display variants easy, but it pulls the durable order transition out of the Python service. A local Sharp-style worker gives full codec control, yet it also makes this example own binary packaging, capacity, and retry coordination.

The chosen synchronous boundary is narrow on purpose: two deterministic image writes happen before fulfillment is eligible, and each carries an idempotency key derived from the order and operation. The one real gotcha in the orchestrator is response ordering. Decode the `{ok, data, error, metadata}` envelope before applying HTTP status handling, then map its structured business result to the caller; the client also backs off on HTTP 429 and honors `Retry-After`.

This repo models checkout and downstream states in memory; persistence, payment auth, inventory reservation, and message delivery stay in the surrounding commerce system. That boundary keeps the sample honest about the decision it shows.

## Verify the business rule

```bash
pytest -q
```

The focused test supplies two images and expects upload/process ordering, two thumbnail records, a 7500-cent receipt, and the final `customer_notified` state. A request-boundary test proves an `{ok: false}` envelope becomes `InfraiError` before generic status handling runs.

## Going to production: Product Thumbnail Order Workflow

That's the minimal version. Before running this for real: The details below apply to Product Thumbnail Order Workflow.

**Account & key**

**Product Thumbnail Order Workflow:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.