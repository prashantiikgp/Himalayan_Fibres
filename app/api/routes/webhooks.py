"""Wix webhook endpoints."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    AbandonedCart,
    Contact,
    ConsentStatus,
    Order,
    WebhookEvent,
    WebhookSource,
)
from app.workers.tasks import (
    send_cart_abandoned_email,
    send_welcome_email,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


def compute_payload_hash(payload: dict) -> str:
    """Compute SHA256 hash of payload for idempotency."""
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(payload_str.encode()).hexdigest()


async def check_idempotency(
    db: DBSession,
    event_id: str,
    payload_hash: str,
) -> bool:
    """Check if webhook event was already processed. Returns True if duplicate."""
    result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.event_id == event_id,
            WebhookEvent.payload_hash == payload_hash,
        )
    )
    return result.scalar_one_or_none() is not None


async def record_webhook_event(
    db: DBSession,
    source: WebhookSource,
    event_type: str,
    event_id: str,
    payload_hash: str,
    raw_payload: dict,
) -> WebhookEvent:
    """Record webhook event for idempotency and debugging."""
    event = WebhookEvent(
        source=source,
        event_type=event_type,
        event_id=event_id,
        payload_hash=payload_hash,
        raw_payload=raw_payload,
    )
    db.add(event)
    await db.flush()
    return event


async def get_or_create_contact(
    db: DBSession,
    email: str,
    name: str | None = None,
    consent_source: str = "wix_checkout",
) -> Contact:
    """Get existing contact or create new one."""
    result = await db.execute(select(Contact).where(Contact.email == email))
    contact = result.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            email=email,
            name=name,
            consent_status=ConsentStatus.OPTED_IN,
            consent_source=consent_source,
            consent_timestamp=datetime.now(timezone.utc),
        )
        db.add(contact)
        await db.flush()

    return contact


@router.post("/wix/order-created")
async def wix_order_created(
    request: Request,
    db: DBSession,
    x_wix_event_id: str | None = Header(None, alias="x-wix-event-id"),
):
    """
    Handle Wix order created webhook.

    Triggers: Welcome/thank-you email
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("Received order-created webhook", event_id=x_wix_event_id)

    # Generate event ID if not provided
    event_id = x_wix_event_id or payload.get("orderId", f"order-{datetime.now().timestamp()}")
    payload_hash = compute_payload_hash(payload)

    # Check idempotency
    if await check_idempotency(db, event_id, payload_hash):
        logger.info("Duplicate webhook event, skipping", event_id=event_id)
        return {"status": "duplicate", "event_id": event_id}

    # Record webhook event
    webhook_event = await record_webhook_event(
        db,
        source=WebhookSource.WIX,
        event_type="order_created",
        event_id=event_id,
        payload_hash=payload_hash,
        raw_payload=payload,
    )

    # Extract order data (adjust based on actual Wix payload structure)
    # Wix ecom order webhook structure:
    order_data = payload.get("data", payload)
    wix_order_id = order_data.get("orderId") or order_data.get("id", event_id)

    # Get buyer info
    buyer_info = order_data.get("buyerInfo", {})
    contact_email = buyer_info.get("email") or order_data.get("email")
    contact_name = buyer_info.get("firstName", "") + " " + buyer_info.get("lastName", "")
    contact_name = contact_name.strip() or None

    if not contact_email:
        logger.error("No email in order webhook", order_id=wix_order_id)
        webhook_event.last_error = "No email in payload"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email in order payload",
        )

    # Get or create contact
    contact = await get_or_create_contact(db, contact_email, contact_name)

    # Extract line items
    line_items = order_data.get("lineItems", [])
    items = [
        {
            "name": item.get("name"),
            "quantity": item.get("quantity"),
            "price": item.get("price"),
            "image_url": item.get("image", {}).get("url"),
        }
        for item in line_items
    ]

    # Get totals
    totals = order_data.get("totals", {})
    total_value = float(totals.get("total", 0))
    currency = order_data.get("currency", "USD")

    # Create order record
    order = Order(
        wix_order_id=wix_order_id,
        contact_id=contact.id,
        contact_email=contact_email,
        contact_name=contact_name,
        items=items,
        total_value=total_value,
        currency=currency,
        shipping_address=order_data.get("shippingInfo", {}).get("address"),
        raw_payload=payload,
    )
    db.add(order)
    await db.flush()

    # Mark webhook as processed
    webhook_event.is_processed = True
    webhook_event.processed_at = datetime.now(timezone.utc)

    await db.commit()

    # Queue welcome email (async task)
    send_welcome_email.delay(order_id=order.id, contact_id=contact.id)

    logger.info(
        "Order created and welcome email queued",
        order_id=order.id,
        contact_email=contact_email,
    )

    return {
        "status": "success",
        "order_id": order.id,
        "wix_order_id": wix_order_id,
        "email_queued": True,
    }


@router.post("/wix/cart-abandoned")
async def wix_cart_abandoned(
    request: Request,
    db: DBSession,
    x_wix_event_id: str | None = Header(None, alias="x-wix-event-id"),
):
    """
    Handle Wix cart abandoned webhook.

    Triggers: Abandoned cart email sequence (1h, 24h, 72h)
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("Received cart-abandoned webhook", event_id=x_wix_event_id)

    # Generate event ID if not provided
    event_id = x_wix_event_id or payload.get("cartId", f"cart-{datetime.now().timestamp()}")
    payload_hash = compute_payload_hash(payload)

    # Check idempotency
    if await check_idempotency(db, event_id, payload_hash):
        logger.info("Duplicate webhook event, skipping", event_id=event_id)
        return {"status": "duplicate", "event_id": event_id}

    # Record webhook event
    webhook_event = await record_webhook_event(
        db,
        source=WebhookSource.WIX,
        event_type="cart_abandoned",
        event_id=event_id,
        payload_hash=payload_hash,
        raw_payload=payload,
    )

    # Extract cart data
    cart_data = payload.get("data", payload)
    wix_cart_id = cart_data.get("cartId") or cart_data.get("id", event_id)

    # Get buyer email
    buyer_info = cart_data.get("buyerInfo", {})
    contact_email = buyer_info.get("email") or cart_data.get("email")

    if not contact_email:
        logger.warning("No email in cart abandoned webhook", cart_id=wix_cart_id)
        webhook_event.last_error = "No email in payload"
        await db.commit()
        return {"status": "skipped", "reason": "no_email"}

    # Get or create contact
    contact = await get_or_create_contact(
        db, contact_email, consent_source="wix_cart_abandoned"
    )

    # Extract line items
    line_items = cart_data.get("lineItems", [])
    items = [
        {
            "name": item.get("name"),
            "quantity": item.get("quantity"),
            "price": item.get("price"),
            "image_url": item.get("image", {}).get("url"),
        }
        for item in line_items
    ]

    # Get totals
    total_value = float(cart_data.get("subtotal", {}).get("amount", 0))
    currency = cart_data.get("currency", "USD")
    checkout_url = cart_data.get("checkoutUrl")

    # Check if cart already exists (maybe abandoned again)
    result = await db.execute(
        select(AbandonedCart).where(AbandonedCart.wix_cart_id == wix_cart_id)
    )
    existing_cart = result.scalar_one_or_none()

    if existing_cart:
        # Update existing cart
        existing_cart.items = items
        existing_cart.total_value = total_value
        existing_cart.checkout_url = checkout_url
        existing_cart.abandoned_at = datetime.now(timezone.utc)
        cart = existing_cart
    else:
        # Create new abandoned cart
        cart = AbandonedCart(
            wix_cart_id=wix_cart_id,
            contact_id=contact.id,
            contact_email=contact_email,
            items=items,
            total_value=total_value,
            currency=currency,
            checkout_url=checkout_url,
            raw_payload=payload,
        )
        db.add(cart)

    await db.flush()

    # Mark webhook as processed
    webhook_event.is_processed = True
    webhook_event.processed_at = datetime.now(timezone.utc)

    await db.commit()

    # Queue abandoned cart email sequence
    # 1 hour delay
    send_cart_abandoned_email.apply_async(
        kwargs={"cart_id": cart.id, "sequence": 1},
        countdown=settings.cart_abandoned_delay_1h,
    )
    # 24 hour delay
    send_cart_abandoned_email.apply_async(
        kwargs={"cart_id": cart.id, "sequence": 2},
        countdown=settings.cart_abandoned_delay_24h,
    )
    # 72 hour delay
    send_cart_abandoned_email.apply_async(
        kwargs={"cart_id": cart.id, "sequence": 3},
        countdown=settings.cart_abandoned_delay_72h,
    )

    logger.info(
        "Cart abandoned and email sequence queued",
        cart_id=cart.id,
        contact_email=contact_email,
    )

    return {
        "status": "success",
        "cart_id": cart.id,
        "wix_cart_id": wix_cart_id,
        "email_sequence_queued": True,
    }


@router.post("/wix/order-shipped")
async def wix_order_shipped(
    request: Request,
    db: DBSession,
    x_wix_event_id: str | None = Header(None, alias="x-wix-event-id"),
):
    """
    Handle Wix order shipped webhook.

    Triggers: Shipping update email
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("Received order-shipped webhook", event_id=x_wix_event_id)

    # Extract order ID
    order_data = payload.get("data", payload)
    wix_order_id = order_data.get("orderId") or order_data.get("id")

    if not wix_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No order ID in payload",
        )

    # Find existing order
    result = await db.execute(
        select(Order).where(Order.wix_order_id == wix_order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        logger.warning("Order not found for shipping update", wix_order_id=wix_order_id)
        return {"status": "skipped", "reason": "order_not_found"}

    # Update order status
    order.status = "shipped"
    order.shipping_email_sent = True  # Will be set to True after email is sent
    await db.commit()

    # Import here to avoid circular import
    from app.workers.tasks import send_shipping_update_email

    send_shipping_update_email.delay(order_id=order.id)

    return {"status": "success", "order_id": order.id}


@router.get("/health")
async def webhook_health():
    """Health check endpoint for webhook receiver."""
    return {
        "status": "healthy",
        "service": "himalayan-fibers-webhooks",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
