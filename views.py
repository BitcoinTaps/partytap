from http import HTTPStatus

from fastapi import Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from lnbits.core.crud import update_payment_status
from lnbits.core.models import User
from lnbits.core.views.api import api_payment
from lnbits.decorators import check_user_exists

from . import partytap_ext, partytap_renderer
from .crud import get_payment

templates = Jinja2Templates(directory="templates")


@partytap_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return partytap_renderer().TemplateResponse(
        "partytap/index.html",
        {"request": request, "user": user.dict()},
    )


@partytap_ext.get(
    "/{paymentid}", name="partytap.displaypin", response_class=HTMLResponse
)
async def displaypin(request: Request, paymentid: str):
    payment = await get_payment(paymentid)
    if not payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="No payment"
        )
    status = await api_payment(payment.payhash)
    if status["paid"]:
        await update_payment_status(
            checking_id=payment.payhash, pending=True
        )
        return partytap_renderer().TemplateResponse(
            "partytap/paid.html", {"request": request, "pin": payment.pin}
        )
    return partytap_renderer().TemplateResponse(
        "partytap/error.html",
        {"request": request, "pin": "filler", "not_paid": True},
    )