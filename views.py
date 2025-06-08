from http import HTTPStatus

from fastapi import Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from lnbits.core.crud import get_standalone_payment
from lnbits.core.models import User, PaymentState
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
    partytap_payment = await get_payment(paymentid)
    if not partytap_payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="No payment"
        )

    payment = await get_standalone_payment(partytap_payment.payhash)
    if not payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Payment not found."
        )
    status = await payment.check_status()
    if status.success:
        return partytap_renderer().TemplateResponse(
            "partytap/paid.html", {"request": request, "pin": partytap_payment.pin}
        )
    return partytap_renderer().TemplateResponse(
        "partytap/error.html",
        {"request": request, "pin": "filler", "not_paid": True},
    )
    
