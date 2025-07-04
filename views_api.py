from http import HTTPStatus

from fastapi import (
    Depends, 
    HTTPException, 
    Query, 
    Request, 
    WebSocket,
    WebSocketDisconnect
)
from loguru import logger

from lnbits.core.crud import get_user, update_payment_extra
from lnbits.decorators import (
    WalletTypeInfo,
    check_admin,
    require_invoice_key,
    require_admin_key,
)
from lnbits.utils.exchange_rates import (
    currencies
)
from lnbits.core.services import (
    websocket_manager,
    websocket_updater
)

from . import partytap_ext, scheduled_tasks
from .crud import (
    create_device,
    delete_device,
    get_device,
    get_devices,
    update_device
)
from .tasks import (
    task_create_invoice,
    task_send_switches,
    task_make_lnurlw,
    task_create_offline_payment
    
)
from .models import CreateLnurldevice

import json

@partytap_ext.websocket("/api/v1/ws/{item_id}")
async def websocket_connect(websocket: WebSocket, item_id: str):
    try:
        await websocket_manager.connect(websocket, item_id)

        device = await get_device(item_id)            
        if device:
            await task_send_switches(item_id)            
        else:
            logger.info("Incorrect deviceid")
            await websocket_updater(item_id,'{"event":"error","message":"device id does not exist"}')
                    
        while True:
            message = await websocket.receive_text()
            logger.info(f"Received message from websocket: {message}")

            if not device:
                logger.info(f"Ignoring websocket message")
                continue

            try:
                jsobj = json.loads(message)
            except json.decoder.JSONDecodeError:
                logger.warning("Invalid JSON message received. Ignoring")                                        
                continue

            
            

            if not "event" in jsobj:
                logger.warning("No event in message, ignored") 
                continue

            if jsobj["event"] == "acknowledged":
                if not 'payment_hash' in jsobj:
                    logger.error("Required field: 'payment_hash' not present in message")
                    continue  
                await update_payment_extra(payment_hash=jsobj["payment_hash"], extra = { 'acknowledged':True})
            elif jsobj["event"] == "fulfilled":
                if not 'payment_hash' in jsobj:
                    logger.error("Required field: 'payment_hash' not present in message")
                    continue  
                await update_payment_extra(payment_hash=jsobj["payment_hash"], extra = { 'fulfilled':True})
            elif jsobj["event"] == "createinvoice":
                if not "switch_id" in jsobj:
                    logger.error(f"Required field: 'switch_id' not present in message")
                    continue          
                logger.info(f"Device id: {item_id}")
                await task_create_invoice(item_id,jsobj["switch_id"])
            elif jsobj["event"] == "lnurlw":
                logger.info("Processing LNURLW for payment");
                for field in ["payment_request","lnurlw"]:
                    logger.info(jsobj[field])
                    if not field in jsobj:
                        logger.error(f"Required field: '{field}' not present in message")
                        continue
                logger.info("making the call")
                await task_make_lnurlw(device.id,jsobj["payment_request"],jsobj["lnurlw"])
            else:                
                logger.warning(f"Unknown event type {jsobj['event']} ignored")

    except WebSocketDisconnect as err:
        logger.warning(f"WebSocket disconnected: code {err.code}, reason {err.reason}")
        websocket_manager.disconnect(websocket)


@partytap_ext.get("/api/v1/currencies")
async def api_list_currencies_available():
    return list(currencies.keys())


@partytap_ext.post("/api/v1/device", dependencies=[Depends(require_admin_key)])
async def api_lnurldevice_create(data: CreateLnurldevice, req: Request):
    return await create_device(data, req)


@partytap_ext.put(
    "/api/v1/device/{device_id}", dependencies=[Depends(require_admin_key)]
)
async def api_device_update(
    data: CreateLnurldevice, device_id: str, req: Request
):
    device = await update_device(device_id, data, req)
    await task_send_switches(device_id)
    return device


@partytap_ext.get("/api/v1/device/{device_id}/payment")
async def api_lnurldevice_offline_payment(req: Request, device_id: str, encrypted: str, iv: str):
    return await task_create_offline_payment(req, device_id, encrypted, iv)

@partytap_ext.get("/api/v1/device")
async def api_lnurldevices_retrieve(
    req: Request, wallet: WalletTypeInfo = Depends(require_invoice_key)
):
    user = await get_user(wallet.wallet.user)
    assert user, "Lnurldevice cannot retrieve user"
    devices = await get_devices(user.wallet_ids)
    for device in devices:
        device.websocket = 0
        for connection in websocket_manager.active_connections:
            if connection.path_params["item_id"] == device.id:
                device.websocket += 1
    return devices


@partytap_ext.get(
    "/api/v1/device/{lnurldevice_id}", dependencies=[Depends(require_invoice_key)]
)
async def api_lnurldevice_retrieve(req: Request, lnurldevice_id: str):
    device = await get_device(lnurldevice_id)
    if not device:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="device does not exist"
        )

    device.websocket = 0
    for connection in websocket_manager.active_connections:
        if connection.path_params["item_id"] == device.id:
            device.websocket += 1

    return device

@partytap_ext.get(
    "/api/v1/device/{lnurldevice_id}/switches"
)
async def api_lnurldevice_switches(req: Request, lnurldevice_id: str):
    lnurldevice = await get_device(lnurldevice_id)
    if not lnurldevice:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="lnurldevice does not exist"
        )

    connectdevice = {
        "switches": lnurldevice.switches,
        "key":lnurldevice.key
    }

    return connectdevice

@partytap_ext.get(
    "/api/v1/order/{payment_hash}/received"
)
async def api_payment_received(req: Request, payment_hash: str):
    logger.info("Payment acknowledged by tap");
    await update_payment_extra(payment_hash=payment_hash, extra = { 'acknowledged':True})
    return 1;

@partytap_ext.get(
    "/api/v1/order/{payment_hash}/fulfilled"
)
async def api_payment_fulfilled(req: Request, payment_hash: str):
    logger.info("Payment fulfilled by tap");
    await update_payment_extra(payment_hash=payment_hash, extra = { 'fulfilled':True})
    return 1;


@partytap_ext.delete(
    "/api/v1/device/{lnurldevice_id}", dependencies=[Depends(require_admin_key)]
)
async def api_lnurldevice_delete(req: Request, lnurldevice_id: str):
    lnurldevice = await get_device(lnurldevice_id)
    if not lnurldevice:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Lnurldevice does not exist."
        )

    await delete_device(lnurldevice_id)


@partytap_ext.delete(
    "/api/v1", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_stop():
    for t in scheduled_tasks:
        try:
            t.cancel()
        except Exception as ex:
            logger.warning(ex)

    return {"success": True}
