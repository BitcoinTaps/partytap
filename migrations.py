import json

from lnbits.db import Database

async def m001_initial(db):
    """
    Initial device table.
    """
    await db.execute(
        f"""
        CREATE TABLE partytap.device (
            id TEXT NOT NULL PRIMARY KEY,
            key TEXT NOT NULL,
            title TEXT NOT NULL,
            wallet TEXT NOT NULL,
            currency TEXT NOT NULL,
            switches TEXT,
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )

    
    await db.execute(
        f"""
        CREATE TABLE partytap.payment (
            id TEXT NOT NULL PRIMARY KEY,
            deviceid TEXT NOT NULL,
            switchid TEXT NOT NULL,
            payhash TEXT,
            payload TEXT NOT NULL,
            sats {db.big_int},
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )

async def m002_redux(db):
     await db.execute(
        "ALTER TABLE partytap.payment ADD COLUMN pin TEXT DEFAULT '';"
    )

async def m003_redux(db):
     await db.execute(
        "ALTER TABLE partytap.device ADD COLUMN branding TEXT DEFAULT 'BitcoinTaps';"
    )
    
