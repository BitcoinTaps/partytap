import asyncio

from lnbits.core.models import Payment
from lnbits.core.services import websocketUpdater
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener
from lnbits.core.crud import get_user, update_payment_extra
from lnbits.utils.exchange_rates import fiat_amount_as_satoshis
from lnbits.core.services import create_invoice
import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from hashlib import sha256
from fastapi import HTTPException, Query, Request
from http import HTTPStatus


from .crud import (
    get_payment, 
    update_payment,
    get_device,
    create_payment,
    create_payment_memo,
    create_payment_metadata
)


from loguru import logger
import json

async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    # Check that the payment is intended for this extension
    if payment.extra.get("tag") != "PartyTap":
        return

    device_payment = await get_payment(payment.extra["id"])

    if not device_payment:
        return
    if device_payment.payhash == "used":
        return

    await update_payment_extra(payment_hash=payment.payment_hash, extra = { 'received':True})        

    message = json.dumps({
        'event': "paid",
        'payment_hash': payment.payment_hash,
        'payload': device_payment.payload
    })
    logger.info(message)
    return await websocketUpdater(
        device_payment.deviceid,
        message    
    )

async def task_create_offline_payment(request: Request, device_id: str, encrypted: str, iv: str):
    # decrypt with deviceid
    device = await get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="device does not exist"
        )
    
    # convert IV to byte string
    ivBytes = bytes.fromhex(iv)
    keyBytes = str.encode(device.key[:16])
    encryptedBytes = bytes.fromhex(encrypted)

    # we're using AES CBC mode
    cipher = Cipher(algorithms.AES(keyBytes), modes.CBC(ivBytes))
    decryptor = cipher.decryptor()
    decrypted_message = decryptor.update(encryptedBytes) + decryptor.finalize()

    if ( decrypted_message[16:].hex() != sha256(decrypted_message[:16]).hexdigest() ):
        logger.info(f"Incorrect message hash, message ignored")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Incorrect input"
        )

    switch_id = decrypted_message[0:8].decode()
    switch = None
    if device.switches:
        for _switch in device.switches:
            if ( _switch.id == switch_id ):
                switch = _switch
                break
    if not switch:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="switch does not exist"
        )

    # extract PIN    
    decrypted_pin_part = decrypted_message[9:16].decode()
    result = decrypted_pin_part.find(':')
    if result == -1:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Incorrect payload"
        )
    secret_pin = decrypted_pin_part[:result]

    # determine price
    price_msat = int((
        await fiat_amount_as_satoshis(float(switch.amount), device.currency)
        if device.currency != "sat"
        else float(switch.amount)
    ) * 1000)

    # create payment
    payment = await create_payment(
        device_id=device.id,
        switch_id=switch.id,
        payload=switch.duration,
        pin=secret_pin,
        sats=price_msat,
        payhash="created"
    )

    return {
        "tag": "payRequest",
        "callback": str(request.url_for(
            "partytap.lnurl_callback", paymentid=payment.id
        )),
        "minSendable": price_msat,
        "maxSendable": price_msat,
        "metadata": create_payment_metadata(device,switch)
    }

async def task_create_invoice(device_id: str, switch_id: str):
    logger.info(f"Create invoice for device: {device_id} and switch: {switch_id}")
    device = await get_device(device_id)
    if not device:
        logger.warning("No device found")
        return
    
    switch = None
    if device.switches:
        for _switch in device.switches:
            if ( _switch.id == switch_id ):
                switch = _switch
                break
    if not switch:
        logger.warning("No switch found")
        return
        
    # determine price
    price_msat = int((
        await fiat_amount_as_satoshis(float(switch.amount), device.currency)
        if device.currency != "sat"
        else float(switch.amount)
    ) * 1000)

    # create payment
    payment = await create_payment(
        device_id=device.id,
        switch_id=switch.id,
        payload=switch.duration,
        sats=price_msat,
        payhash="created"
    )


    # create invoice
    payment_hash, payment_request = await create_invoice(
        wallet_id=device.wallet,
        amount=int(payment.sats / 1000),
        memo=create_payment_memo(device,switch),
        unhashed_description=create_payment_metadata(device,switch).encode(),
        extra={
            "tag": "PartyTap",
            "Device": device.id,
            "Switch": switch.id,
            "amount": switch.amount,
            "currency": device.currency,
            "id": payment.id,
            "received": False,
            "acknowledged": False,
            "fulfilled": False
        },
    )

    payment = await update_payment(
        payment_id=payment.id, payhash=payment_hash
    )

    await websocketUpdater(
        device_id,
        json.dumps({
            "event":"invoice",
            "pr": payment_request,
            "payment_hash": payment_hash
        })
    )

    logger.info("Invoice created and sent")

async def task_send_switches(device_id: str):
    logger.info(f"Sending switches config for device: {device_id}")

    device = await get_device(device_id)

    if not device:
        logger.warning("No device found")
        return
    
    message = {
        "event":"switches",
        "switches": [],
        "key": device.key,
        "version": "842370"
    }

    for _switch in device.switches:
        message["switches"].append({
            "label": _switch.label,
            "lnurl": _switch.lnurl,
            "id":  _switch.id,
            "duration": _switch.duration,
            "amount": _switch.amount,
            "currency": device.currency
        })

    logger.info("Calling websocket updater")
    try:
        await websocketUpdater(device_id,json.dumps(message))
    except Exception as err:
        logger.error("Websocket updater failed")
        logger.error(err)

    
async def task_make_lnurlw(device_id: str, payment_request: str,lnurlw: str):
    logger.info("task_make_lnurlw")

    device = await get_device(device_id)
    if not device:
        logger.warning("No device found")
        return
    
    # validate lnurlw
    if not lnurlw.startswith("lnurlw://"):
        logger.error("lnurlw does not start with 'lnurlw://'")
        return

    logger.info(lnurlw)
    
    # convert lnurlw into https URL
    url = 'https://' + lnurlw[9:]
    logger.info(f"Payment URL: {url}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            result = response.json()
        except (httpx.ConnectError, httpx.RequestError):
            logger.error("http request failed")
            return

    logger.info(json.dumps(result))

    if 'status' in result and result['status'] == "ERROR":
        logger.error("Error in LNURLW response")
        if 'reason' in result:
            logger.error(f"Reason: {result['reason']}")


        await websocketUpdater(
            device_id,
            json.dumps({
                "event":"paymentfailed",
                "pr": payment_request
            })
        )

        return
    
    for field in ['k1','callback']:
        if not field in result:
            logger.error(f"No {field} in result")

            await websocketUpdater(
                device_id,
                json.dumps({
                    "event":"paymentfailed",
                    "pr": payment_request
                })
            )
            
            return
    
    # construct callback url
    url = f"{result['callback']}?k1={result['k1']}&pr={payment_request}"
    logger.info(f"callback URL: {url}")
    
    # just make the call and forget about it 
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            result = response.json()
            logger.info(f"Payment response {result}")

            if 'status' in result and result['status'] == "ERROR":
                logger.error("Error in LNURLW response")
                if 'reason' in result:
                    logger.error(f"Reason: {result['reason']}")

                    
                await websocketUpdater(
                    device_id,
                    json.dumps({
                        "event":"paymentfailed",
                        "pr": payment_request
                    })
                )

                return

            
        except (httpx.ConnectError, httpx.RequestError):
            logger.error("http request failed")

            await websocketUpdater(
                device_id,
                json.dumps({
                    "event":"paymentfailed",
                    "pr": payment_request
                })
            )
            
            return

    # now the websocket should take it over from here
