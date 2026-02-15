# 📱 Install APK on Android Mobile

## **Method 1: Using ADB (Recommended)**

### **Prerequisites:**
1. Enable **Developer Options** on your Android phone:
   - Go to **Settings** → **About Phone**
   - Tap **Build Number** 7 times
   - Go back to **Settings** → **Developer Options**
   - Enable **USB Debugging**

2. Install ADB on your computer:
   ```bash
   # macOS
   brew install android-platform-tools
   
   # Or download from: https://developer.android.com/studio/releases/platform-tools
   ```

### **Installation Steps:**

1. **Connect your phone via USB**

2. **Verify connection:**
   ```bash
   adb devices
   # Should show your device ID
   ```

3. **Install the APK:**
   ```bash
   cd android_app
   adb install -r "app/build/outputs/apk/debug/app-debug.apk"
   ```

   Or if using the existing APK:
   ```bash
   adb install -r "Gundu Ata NoIcon Unaligned.apk"
   ```

---

## **Method 2: Direct File Transfer (Easier)**

### **Steps:**

1. **Copy APK to your phone:**
   - Connect phone via USB
   - Copy APK file to phone's Download folder
   - Or use AirDrop/Share via email/cloud storage

2. **Enable Unknown Sources:**
   - Go to **Settings** → **Security** (or **Privacy**)
   - Enable **Install Unknown Apps** or **Unknown Sources**
   - Select your file manager (Files, Chrome, etc.)

3. **Install APK:**
   - Open **Files** app on your phone
   - Navigate to **Downloads** folder
   - Tap on the APK file
   - Tap **Install**
   - Tap **Install** again to confirm

---

## **Method 3: Using QR Code (Wireless)**

1. **Host APK on local server:**
   ```bash
   cd android_app
   python3 -m http.server 8000
   ```

2. **Generate QR Code:**
   - Visit: https://qr-code-generator.com/
   - Enter URL: `http://YOUR_COMPUTER_IP:8000/app-debug.apk`
   - Scan QR code with phone

3. **Download and Install:**
   - Phone will download APK
   - Open Downloads folder
   - Tap APK and install

---

## **Available APK Files:**

1. **Latest Debug Build:**
   - `android_app/app/build/outputs/apk/debug/app-debug.apk`
   - ✅ **Use this one** - Contains latest fixes (HTTP base URL, timeout settings)

2. **Existing APKs:**
   - `android_app/Gundu Ata NoIcon Unaligned.apk`
   - `android_app/Gundu Ata NoIcon Aligned.apk`
   - `android_app/Gundu Ata.apk`

---

## **After Installation:**

1. **Open the app** from app drawer
2. **Test Login:**
   - Try logging in with valid credentials
   - Should connect without timeout now
   - Base URL is now HTTP (faster, no SSL issues)

---

## **Troubleshooting:**

### **"App not installed" error:**
- Uninstall old version first
- Enable "Install Unknown Apps" in settings
- Check if phone has enough storage

### **"Parse error":**
- APK might be corrupted
- Rebuild APK: `cd android_app && ./gradlew assembleDebug`

### **"App keeps stopping":**
- Check logcat: `adb logcat | grep sikwin`
- Rebuild with latest code

---

## **Quick Install Command:**

```bash
# Navigate to project
cd android_app

# Rebuild APK (if needed)
./gradlew assembleDebug

# Install via ADB
adb install -r "app/build/outputs/apk/debug/app-debug.apk"
```

---

**Note:** The latest APK includes:
- ✅ HTTP base URL (no HTTPS timeout issues)
- ✅ 30-second timeout settings
- ✅ Fixed connection timeout problems
