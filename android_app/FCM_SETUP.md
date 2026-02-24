# Firebase Cloud Messaging (FCM) Setup

Push notifications are integrated. Complete these steps to enable them:

## 1. Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project (or use existing)
3. Add an **Android** app with package name: `com.sikwin.app`
4. Download `google-services.json` and place it in `android_app/app/`

## 2. Run Migration

```bash
cd backend
python manage.py migrate
```

## 3. Send Notifications from Backend

Install Firebase Admin SDK:

```bash
pip install firebase-admin
```

Create a utility (e.g. `backend/accounts/fcm_utils.py`):

```python
import firebase_admin
from firebase_admin import credentials, messaging

# Initialize once (e.g. in Django startup)
def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate("path/to/serviceAccountKey.json")
        firebase_admin.initialize_app(cred)

def send_push_to_user(user, title, body, data=None):
    from .models import DeviceToken
    tokens = DeviceToken.objects.filter(user=user).values_list('fcm_token', flat=True)
    for token in tokens:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )
        messaging.send(message)
```

Get `serviceAccountKey.json` from Firebase Console → Project Settings → Service Accounts → Generate new private key.

## 4. Example: Notify on Deposit Approval

In your deposit approval view:

```python
from accounts.fcm_utils import send_push_to_user

# After approving deposit
send_push_to_user(
    deposit.user,
    "Deposit Approved!",
    f"₹{deposit.amount} has been added to your wallet."
)
```

## 5. Build the App

After adding `google-services.json`:

```bash
cd android_app
./gradlew assembleDebug
```
