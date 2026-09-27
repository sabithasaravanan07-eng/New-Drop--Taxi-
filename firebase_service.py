import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


BASE_DIR = Path(__file__).resolve().parent


def get_firestore():
    credential_path = Path(
        os.environ.get(
            "FIREBASE_SERVICE_ACCOUNT",
            BASE_DIR / "firebase-service-account.json",
        )
    )
    if not credential_path.exists():
        raise FileNotFoundError(
            f"Firebase service-account file not found: {credential_path}"
        )

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(credential_path)))

    return firestore.client()
