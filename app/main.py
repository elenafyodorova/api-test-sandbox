from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncpg
from datetime import date
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://qa_user:qa_pass123@db:5432/logistics"
)

app = FastAPI(
    title="Smart Logistics Orders API",
    version="2.0.0",
    description="Тестовый стенд для практики Postman — контроллер /api/v2/orders"
)

pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

async def get_conn():
    async with pool.acquire() as conn:
        yield conn

# ──────────────────────────────────────────────
# Кастомные обработчики ошибок
# Возвращаем формат Microsoft Graph: {error: {code, message, target}}
# ──────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Возвращает detail напрямую, если это уже dict — иначе оборачивает."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "error", "message": str(exc.detail)}}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """422 Pydantic → 400 badRequest в нашем формате."""
    errors = exc.errors()
    target = errors[0]["loc"][-1] if errors else "body"
    message = errors[0]["msg"] if errors else "Validation error"
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "badRequest",
                "message": message,
                "target": str(target),
                "innererror": {"details": errors}
            }
        }
    )

# ──────────────────────────────────────────────
# Pydantic-модели
# ──────────────────────────────────────────────

VALID_ORDER_TYPES = ("auction", "direct", "tender")
VALID_STATUSES    = ("new", "in_transit", "delivered", "cancelled")

class OrderCreate(BaseModel):
    customerId: int
    carrierId: int
    driverId: int
    originCityId: int
    destinationCityId: int
    weightKg: float = Field(..., gt=0, le=20000, description="Вес в кг, максимум 20 000")
    volumeM3: float = Field(..., gt=0, le=82,    description="Объём в м³, максимум 82")
    orderType: str  = Field(..., description="auction | direct | tender")
    loadingDate: date
    baseRateWithVat: Optional[float] = None

class OrderUpdate(BaseModel):
    status: Optional[str]  = None
    weightKg: Optional[float] = Field(None, gt=0, le=20000)
    volumeM3: Optional[float] = Field(None, gt=0, le=82)
    loadingDate: Optional[date] = None

# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def format_order(row: asyncpg.Record) -> dict:
    """asyncpg Record → camelCase dict."""
    r = dict(row)
    return {
        "id":                  r["id"],
        "customerId":          r["customer_id"],
        "customerName":        r.get("customer_name"),
        "carrierId":           r["carrier_id"],
        "driverId":            r["driver_id"],
        "originCity":          r.get("origin_city"),
        "destinationCity":     r.get("destination_city"),
        "weightKg":            float(r["weight_kg"])   if r["weight_kg"]   else None,
        "volumeM3":            float(r["volume_m3"])   if r["volume_m3"]   else None,
        "status":              r["status"],
        "orderType":           r.get("order_type"),
        "price":               float(r["price"])       if r["price"]       else None,
        "baseRateWithVat":     float(r["base_rate_with_vat"])     if r.get("base_rate_with_vat")     else None,
        "baseRateWithoutVat":  float(r["base_rate_without_vat"])  if r.get("base_rate_without_vat")  else None,
        "loadingDate":         r["loading_date"].isoformat()  if r["loading_date"]  else None,
        "createdAt":           r["created_at"].isoformat()   if r["created_at"]    else None,
        "deletedAt":           r["deleted_at"].isoformat()   if r.get("deleted_at") else None,
    }

async def fetch_order_or_raise(order_id: int, conn) -> dict:
    """Загружает заказ с JOIN-ами; бросает 404 или 410 если нужно."""
    row = await conn.fetchrow("""
        SELECT o.*,
               c.name  AS customer_name,
               oc.name AS origin_city,
               dc.name AS destination_city
        FROM orders o
        LEFT JOIN customers c  ON c.id  = o.customer_id
        LEFT JOIN cities    oc ON oc.id = o.origin_city_id
        LEFT JOIN cities    dc ON dc.id = o.destination_city_id
        WHERE o.id = $1
    """, order_id)

    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": {
                "code": "notFound",
                "message": f"Order {order_id} not found.",
                "target": "id"
            }}
        )

    if dict(row).get("deleted_at"):
        raise HTTPException(
            status_code=410,
            detail={"error": {
                "code": "gone",
                "message": f"Order {order_id} has been deleted and is no longer available.",
                "target": "id"
            }}
        )

    return row

# ──────────────────────────────────────────────
# GET /api/v2/orders — List
# ──────────────────────────────────────────────

@app.get("/api/v2/orders", summary="Список заказов")
async def list_orders(conn=Depends(get_conn)):
    """
    Возвращает все не удалённые заказы.
    При отсутствии записей возвращает пустой массив [].
    """
    rows = await conn.fetch("""
        SELECT o.*,
               c.name  AS customer_name,
               oc.name AS origin_city,
               dc.name AS destination_city
        FROM orders o
        LEFT JOIN customers c  ON c.id  = o.customer_id
        LEFT JOIN cities    oc ON oc.id = o.origin_city_id
        LEFT JOIN cities    dc ON dc.id = o.destination_city_id
        WHERE o.deleted_at IS NULL
        ORDER BY o.created_at DESC
    """)
    return [format_order(r) for r in rows]

# ──────────────────────────────────────────────
# GET /api/v2/orders/{id} — Get
# ──────────────────────────────────────────────

@app.get("/api/v2/orders/{order_id}", summary="Получить заказ по ID")
async def get_order(order_id: int, conn=Depends(get_conn)):
    """
    200 — заказ найден
    404 — заказ не существует
    410 — заказ был удалён (мягкое удаление)
    """
    row = await fetch_order_or_raise(order_id, conn)
    return format_order(row)

# ──────────────────────────────────────────────
# POST /api/v2/orders — Create
# ──────────────────────────────────────────────

@app.post("/api/v2/orders", status_code=201, summary="Создать заказ")
async def create_order(order: OrderCreate, conn=Depends(get_conn)):
    """
    201 — заказ создан
    400 — ошибка валидации (невалидный orderType или нарушение ограничений полей)
    409 — конфликт (в данной реализации не применяется, т.к. ID генерирует БД)
    """
    if order.orderType not in VALID_ORDER_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"error": {
                "code": "badRequest",
                "message": f"orderType must be one of: {', '.join(VALID_ORDER_TYPES)}.",
                "target": "orderType"
            }}
        )

    price = order.baseRateWithVat or round(order.weightKg * 6.5, 2)
    rate_without_vat = round(price / 1.2, 2)

    row = await conn.fetchrow("""
        INSERT INTO orders (
            customer_id, carrier_id, driver_id,
            origin_city_id, destination_city_id,
            weight_kg, volume_m3, status, order_type,
            price, base_rate_with_vat, base_rate_without_vat,
            loading_date, created_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,'new',$8,$9,$9,$10,$11,NOW())
        RETURNING id
    """,
        order.customerId, order.carrierId, order.driverId,
        order.originCityId, order.destinationCityId,
        order.weightKg, order.volumeM3, order.orderType,
        price, rate_without_vat, order.loadingDate
    )

    return format_order(await fetch_order_or_raise(row["id"], conn))

# ──────────────────────────────────────────────
# PUT /api/v2/orders/{id} — Update
# ──────────────────────────────────────────────

@app.put("/api/v2/orders/{order_id}", summary="Обновить заказ")
async def update_order(order_id: int, body: OrderUpdate, conn=Depends(get_conn)):
    """
    200 — заказ обновлён, возвращается обновлённая модель
    400 — невалидный status
    404 — заказ не найден
    410 — заказ удалён
    """
    await fetch_order_or_raise(order_id, conn)  # проверяем существование и deleted_at

    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": {
                "code": "badRequest",
                "message": f"status must be one of: {', '.join(VALID_STATUSES)}.",
                "target": "status"
            }}
        )

    updates = {}
    if body.status      is not None: updates["status"]       = body.status
    if body.weightKg    is not None: updates["weight_kg"]    = body.weightKg
    if body.volumeM3    is not None: updates["volume_m3"]    = body.volumeM3
    if body.loadingDate is not None: updates["loading_date"] = body.loadingDate

    if updates:
        set_clause = ", ".join(
            f"{col} = ${i + 2}" for i, col in enumerate(updates.keys())
        )
        await conn.execute(
            f"UPDATE orders SET {set_clause} WHERE id = $1",
            order_id, *updates.values()
        )

    return format_order(await fetch_order_or_raise(order_id, conn))

# ──────────────────────────────────────────────
# DELETE /api/v2/orders/{id} — Soft Delete
# ──────────────────────────────────────────────

@app.delete("/api/v2/orders/{order_id}", status_code=204, summary="Удалить заказ (мягко)")
async def delete_order(order_id: int, conn=Depends(get_conn)):
    """
    204 — заказ удалён
    404 — заказ не найден
    410 — заказ уже был удалён ранее
    """
    await fetch_order_or_raise(order_id, conn)
    await conn.execute(
        "UPDATE orders SET deleted_at = NOW() WHERE id = $1",
        order_id
    )
    return Response(status_code=204)

# ──────────────────────────────────────────────
# HEAD /api/v2/orders/{id}
# ──────────────────────────────────────────────

@app.head("/api/v2/orders/{order_id}", status_code=204, summary="Проверить существование заказа")
async def head_order(order_id: int, conn=Depends(get_conn)):
    """204 — существует, тело ответа пустое."""
    exists = await conn.fetchval(
        "SELECT 1 FROM orders WHERE id = $1 AND deleted_at IS NULL",
        order_id
    )
    if not exists:
        return Response(status_code=404)
    return Response(status_code=204)
