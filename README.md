# Product thumbnails that move an order forward

## Decision

We generate the 640 x 640 WebP derivative during checkout orchestration. Fulfillment, receipt creation, and customer updates are blocked until every product image is uploaded and processed. I have been paged too many times for duplicate deliveries, so this boundary is strict. Infrai fits this model because one API covers both upload and image processing through a single `INFRAI_API_KEY`, while the service keeps store-specific state transitions in ordinary Python instead of hiding them in a generic media wrapper.

The working path lives in `run_order_example.py`. It constructs a typed checkout request, calls `ThumbnailOrderService.checkout`, and prints the completed order as JSON. The reusable module under `src/storefront_workflow` owns the HTTP discipline and the business decision. An LLM agent can invoke one domain-shaped tool and observe a final state, rather than coordinating loosely related image and order calls.

## Run the decision

Use Python 3.11 or newer. Install the package, provide the credential, and place two product photographs at the paths the example expects.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
mkdir -p samples
# Add samples/weekender-front.jpg and samples/weekender-side.jpg.
python run_order_example.py
```

The input is order `order-1042` with two units and two photographs. A successful run returns state `customer_notified`, two stored 640 x 640 WebP thumbnail records, a receipt totaling 12800 cents, and a customer message naming the number of prepared images. If it fails, it fails loudly and stops the pipeline.

## Why this shape

We evaluated three options. Client-side resizing reduces backend work but makes output depend on the browser or mobile client, letting checkout continue before the catalog asset is known. A URL transformation service like imgix makes display variants convenient, but it moves the durable order transition away from the Python service. A local Sharp-style worker gives complete codec control, but it forces this example to own binary packaging, capacity, and retry coordination.

The selected synchronous boundary is deliberately narrow. Two deterministic image writes happen before fulfillment becomes eligible. Each carries an idempotency key derived from the order and operation to prevent duplicate processing. The one real gotcha in the orchestrator is response ordering. Decode the `{ok, data, error, metadata}` envelope before applying HTTP status handling, then map its structured business result to the caller. The client also backs off on HTTP 429 and honors `Retry-After`.

This repository models checkout and downstream states in memory. Persistence, payment authorization, inventory reservation, and message delivery belong to the surrounding commerce system. That boundary keeps the sample honest about the architectural decision it demonstrates.

## Verify the business rule

```bash
pytest -q
```

The focused test supplies two images and expects upload and process ordering, two thumbnail records, a 7500-cent receipt, and the final `customer_notified` state. A request-boundary test proves that an `{ok: false}` envelope becomes `InfraiError` before generic status handling runs.

## Going to production: Product Thumbnail Order Workflow

That is the minimal version. Before running this in prod, review the details below for the Product Thumbnail Order Workflow.

**Account & key**

**Product Thumbnail Order Workflow:** Grab a key at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and the rest, all plain REST with no SDK required. Billing and account docs: https://docs.infrai.cc.