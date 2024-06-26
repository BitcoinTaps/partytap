import json
from typing import List, Optional

import shortuuid
from fastapi import Request
from lnurl import encode as lnurl_encode

from lnbits.helpers import urlsafe_short_hash

from . import db
from .models import CreateLnurldevice, Lnurldevice, LnurldevicePayment
from loguru import logger



async def create_device(data: CreateLnurldevice, req: Request) -> Lnurldevice:
    logger.debug("create_device")
    device_id = shortuuid.uuid()[:8]
    device_key = urlsafe_short_hash()

    if data.switches:
        url = str(req.url_for("partytap.lnurl_v2_params", device_id=device_id))
        for _switch in data.switches:
            _switch.id = shortuuid.uuid()[:8]
            _switch.lnurl = lnurl_encode(
                url
                + "?switch_id="
                + str(_switch.id)
            )

    await db.execute(
        "INSERT INTO partytap.device (id, key, title, wallet, currency, branding, switches) VALUES (?, ?, ?, ?, ?, ?,?)",
        (
            device_id,
            device_key,
            data.title,
            data.wallet,
            data.currency,
            data.branding,
            json.dumps(data.switches, default=lambda x: x.dict()),
        ),
    )

    device = await get_device(device_id)
    assert device, "Lnurldevice was created but could not be retrieved"
    return device


async def update_device(
    device_id: str, data: CreateLnurldevice, req: Request
) -> Lnurldevice:
    
    if data.switches:
        url = str(req.url_for("partytap.lnurl_v2_params", device_id=device_id))
        for _switch in data.switches:
            if _switch.id is None:
                _switch.id = shortuuid.uuid()[:8]            
                _switch.lnurl = lnurl_encode(
                    url
                    + "?switch_id="
                    + str(_switch.id)
                )

    await db.execute(
        """
        UPDATE partytap.device SET
            title = ?,
            wallet = ?,
            currency = ?,
            branding = ?,
            switches = ?
        WHERE id = ?
        """,
        (
            data.title,
            data.wallet,
            data.currency,
            data.branding,
            json.dumps(data.switches, default=lambda x: x.dict()),
            device_id,
        ),
    )
    device = await get_device(device_id)
    assert device, "Lnurldevice was updated but could not be retrieved"
    return device

async def get_device(device_id: str) -> Optional[Lnurldevice]:
    row = await db.fetchone(
        "SELECT * FROM partytap.device WHERE id = ?", (device_id,)
    )
    if not row:
        return None
    device = Lnurldevice(**row)

    return device


async def get_devices(wallet_ids: List[str]) -> List[Lnurldevice]:

    q = ",".join(["?"] * len(wallet_ids))
    rows = await db.fetchall(
        f"""
        SELECT * FROM partytap.device WHERE wallet IN ({q})
        ORDER BY id
        """,
        (*wallet_ids,),
    )

    # this is needed for backwards compabtibility, before the LNURL were cached inside db
    devices = [Lnurldevice(**row) for row in rows]

    return devices


async def delete_device(lnurldevice_id: str) -> None:
    await db.execute(
        "DELETE FROM partytap.device WHERE id = ?", (lnurldevice_id,)
    )


async def create_payment(
    device_id: str,
    switch_id: str,
    payload: Optional[str] = None,
    payhash: Optional[str] = None,
    sats: Optional[int] = 0,
    pin: Optional[str] = ""
) -> LnurldevicePayment:


    payment_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO partytap.payment (
            id,
            deviceid,
            switchid,
            payload,
            payhash,
            sats,
            pin
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (payment_id, device_id, switch_id, payload, payhash, sats, pin),
    )
    payment = await get_payment(payment_id)
    assert payment, "Could not retrieve newly created payment"
    return payment


async def update_payment(
    payment_id: str, **kwargs
) -> LnurldevicePayment:
    q = ", ".join([f"{field[0]} = ?" for field in kwargs.items()])
    await db.execute(
        f"UPDATE partytap.payment SET {q} WHERE id = ?",
        (*kwargs.values(), payment_id),
    )
    dpayment = await get_payment(payment_id)
    assert dpayment, "Couldnt retrieve update LnurldevicePayment"
    return dpayment


async def get_payment(
    lnurldevicepayment_id: str,
) -> Optional[LnurldevicePayment]:
    logger.info(f"get_payment {lnurldevicepayment_id}")
    row = await db.fetchone(
        "SELECT * FROM partytap.payment WHERE id = ?",
        (lnurldevicepayment_id,),
    )
    logger.info(row)
    return LnurldevicePayment(**row) if row else None

async def get_payment_by_p(
    p: str,
) -> Optional[LnurldevicePayment]:
    row = await db.fetchone(
        "SELECT * FROM partytap.payment WHERE payhash = ?",
        (p,),
    )
    return LnurldevicePayment(**row) if row else None
    
async def get_lnurlpayload(
    lnurldevicepayment_payload: str,
) -> Optional[LnurldevicePayment]:
    row = await db.fetchone(
        "SELECT * FROM partytap.payment WHERE payload = ?",
        (lnurldevicepayment_payload,),
    )
    return LnurldevicePayment(**row) if row else None


def create_payment_memo(device, switch) -> str:
    memo = ""
    if device.title:
        memo += device.title
    if switch.label:
        memo += " "
        memo += switch.label
    return memo

def create_payment_metadata(device, switch):
    return json.dumps([["text/plain", create_payment_memo(device,switch)]])



