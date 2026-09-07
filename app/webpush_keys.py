import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.push_models import WebPushKey


def _generate_keypair() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return public_key, private_pem


async def get_webpush_keypair(db: AsyncSession) -> tuple[str, str]:
    row = await db.scalar(select(WebPushKey).where(WebPushKey.id == 1))
    if row is None:
        public_key, private_pem = _generate_keypair()
        row = WebPushKey(id=1, public_key=public_key, private_key_pem=private_pem)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row.public_key, row.private_key_pem
