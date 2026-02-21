package com.sikwin.app.ui.screens

import android.graphics.Bitmap
import android.graphics.drawable.BitmapDrawable
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.text.selection.SelectionContainer
import coil.ImageLoader
import coil.request.ImageRequest
import coil.request.SuccessResult
import java.io.OutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlin.time.Duration.Companion.seconds
import android.net.Uri
import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.runtime.*
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import coil.compose.AsyncImage
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaymentScreen(
    amount: String,
    paymentMethod: String = "UPI",
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onSubmitSuccess: () -> Unit
) {
    var selectedImageUri by remember { mutableStateOf<Uri?>(null) }
    var selectedMethod by remember { mutableStateOf("Paytm") }
    
    val usdtExchangeRate = 95
    val usdtBonusPercent = 0.05
    
    val isUsdt = paymentMethod.contains("USDT", ignoreCase = true)
    
    val usdtAmount = if (isUsdt) {
        try {
            amount.toDouble() / usdtExchangeRate
        } catch (e: Exception) {
            0.0
        }
    } else 0.0

    val bonusAmount = if (isUsdt) {
        try {
            amount.toDouble() * usdtBonusPercent
        } catch (e: Exception) {
            0.0
        }
    } else 0.0
    
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        selectedImageUri = uri
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    
    // Timer state: 10 minutes = 600 seconds
    var timeLeftSeconds by remember { mutableIntStateOf(600) }

    LaunchedEffect(timeLeftSeconds) {
        if (timeLeftSeconds > 0) {
            delay(1000L)
            timeLeftSeconds--
        } else {
            // Redirect to deposit page when timer hits 0
            onBack()
        }
    }

    // Format seconds to MM:SS
    val timeLeft = remember(timeLeftSeconds) {
        val minutes = timeLeftSeconds / 60
        val seconds = timeLeftSeconds % 60
        String.format("%02d:%02d", minutes, seconds)
    }

    LaunchedEffect(Unit) {
        viewModel.fetchPaymentMethods()
        viewModel.clearError()
    }

    fun openUpiApp(packageName: String?, specificUpiId: String?) {
        val upiId = specificUpiId ?: viewModel.paymentMethods.firstOrNull { !it.upi_id.isNullOrBlank() }?.upi_id 
        
        if (upiId.isNullOrBlank()) {
            Toast.makeText(context, "No UPI ID available for payment", Toast.LENGTH_SHORT).show()
            return
        }

        // Create UPI payment URI
        val payeeName = "GunduAta"
        val transactionNote = "Wallet Topup"
        val upiUri = "upi://pay?pa=$upiId&pn=$payeeName&am=$amount&cu=INR&tn=$transactionNote"
        
        // Debug logging
        android.util.Log.d("PaymentScreen", "Opening UPI app - Package: $packageName, UPI URI: $upiUri")
        
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(upiUri))
        
        if (packageName != null) {
            val packageManager = context.packageManager
            try {
                // Check if the specific app is installed
                packageManager.getPackageInfo(packageName, 0)
                
                // App is installed, try to open it specifically
                intent.setPackage(packageName)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)
            } catch (e: Exception) {
                // If specific app is not found or fails to open with package name, 
                // show a toast instead of falling back to chooser to keep it direct as requested
                android.util.Log.e("PaymentScreen", "Error opening specific app $packageName: ${e.message}")
                Toast.makeText(context, "Please install ${getAppName(packageName)} to continue", Toast.LENGTH_LONG).show()
            }
        } else {
            // No specific package, let system choose
            try {
                context.startActivity(Intent.createChooser(intent, "Pay with"))
            } catch (e: Exception) {
                Toast.makeText(context, "No UPI app found. Please install a UPI app.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    fun saveImageToGallery(imageUrl: String) {
        scope.launch {
            try {
                val loader = ImageLoader(context)
                val request = ImageRequest.Builder(context)
                    .data(imageUrl)
                    .size(coil.size.Size.ORIGINAL) // Fetch original full-size image
                    .allowHardware(false)
                    .build()

                val result = (loader.execute(request) as? SuccessResult)?.drawable
                val bitmap = (result as? BitmapDrawable)?.bitmap

                if (bitmap != null) {
                    val filename = "GunduAta_QR_${System.currentTimeMillis()}.jpg"
                    var fos: OutputStream? = null
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        val contentValues = android.content.ContentValues().apply {
                            put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
                            put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
                            put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_PICTURES)
                        }
                        val imageUri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues)
                        fos = imageUri?.let { context.contentResolver.openOutputStream(it) }
                    } else {
                        val imagesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                        val image = java.io.File(imagesDir, filename)
                        fos = java.io.FileOutputStream(image)
                    }

                    fos?.use {
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 100, it)
                        withContext(Dispatchers.Main) {
                            Toast.makeText(context, "QR Code saved to gallery", Toast.LENGTH_SHORT).show()
                        }
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(context, "Failed to load image for saving", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error saving image: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF5F5F5)) // Light background like in image
            .verticalScroll(rememberScrollState())
    ) {
        // Top Bar
        Surface(
            color = Color(0xFF3F51B5), // Blue header like in image
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.Default.ArrowBack, null, tint = Color.White)
                }
                Text(
                    "Payment",
                    color = Color.White,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center
                )
                Text(
                    timeLeft,
                    color = Color.White,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                "Amount Payable",
                color = Color.Black,
                fontSize = 18.sp
            )
            Text(
                "₹$amount",
                color = Color(0xFF0022AA), // Deep blue for amount
                fontSize = 36.sp,
                fontWeight = FontWeight.ExtraBold,
                modifier = Modifier.padding(vertical = 8.dp)
            )

            if (isUsdt) {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    color = Color(0xFFE8F5E9),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, Color(0xFF4CAF50))
                ) {
                    Column(modifier = Modifier.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(stringResource(R.string.usdt_amount_to_pay), color = Color.Black, fontSize = 14.sp)
                        Text("${String.format("%.2f", usdtAmount)} USDT", color = Color(0xFF2E7D32), fontSize = 24.sp, fontWeight = FontWeight.Bold)
                        Text(stringResource(R.string.exchange_rate_label, usdtExchangeRate.toString()), color = Color.Gray, fontSize = 12.sp)
                        if (bonusAmount > 0) {
                            Text(stringResource(R.string.bonus_added, String.format("%.2f", bonusAmount)), color = Color(0xFF2E7D32), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        }
                    }
                }
            }

            Text(
                if (isUsdt) "Please transfer USDT to the address below" else "Please fill in UTR after successful payment",
                color = Color.Black,
                fontSize = 14.sp,
                textAlign = TextAlign.Center
            )
            Text(
                "Use Mobile Scan QR To Pay",
                color = Color.Black,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 4.dp, bottom = 16.dp)
            )

            // QR Code Placeholder or USDT Address
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 16.dp)
                    .border(1.dp, Color.LightGray, RoundedCornerShape(8.dp)),
                color = Color.White
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    if (isUsdt) {
                        val network = if (paymentMethod.contains("TRC20", ignoreCase = true)) "TRC20" else "BEP20"
                        val usdtMethod = viewModel.paymentMethods.firstOrNull { 
                            it.method_type.contains("USDT", ignoreCase = true) && it.method_type.contains(network, ignoreCase = true)
                        }
                        val address = usdtMethod?.usdt_wallet_address?.takeIf { it.isNotBlank() }
                            ?: usdtMethod?.upi_id?.takeIf { it.isNotBlank() }
                            ?: "Please contact support for address"
                        
                        Text(stringResource(R.string.network, network), color = Color.Black, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(8.dp))
                        
                        // QR Code for USDT if available
                        if (usdtMethod?.qr_image != null) {
                            AsyncImage(
                                model = usdtMethod.qr_image,
                                contentDescription = "USDT QR Code",
                                modifier = Modifier.size(200.dp)
                            )
                        } else {
                            Icon(
                                Icons.Default.QrCode2,
                                contentDescription = "QR Code",
                                modifier = Modifier.size(120.dp),
                                tint = Color.Black
                            )
                        }
                        
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(stringResource(R.string.wallet_address), color = Color.Gray, fontSize = 12.sp)
                        SelectionContainer {
                            Text(
                                address,
                                color = Color.Black,
                                fontSize = 14.sp,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.padding(vertical = 4.dp)
                            )
                        }
                        
                        Button(
                            onClick = { 
                                val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                val clip = android.content.ClipData.newPlainText("USDT Address", address)
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "Address copied to clipboard", Toast.LENGTH_SHORT).show()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color.Gray),
                            modifier = Modifier.padding(top = 8.dp)
                        ) {
                            Icon(Icons.Default.ContentCopy, null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(stringResource(R.string.copy_address))
                        }
                    } else if (paymentMethod.contains("BANK", ignoreCase = true)) {
                        // Bank Details
                        val bankMethod = viewModel.paymentMethods.firstOrNull { 
                            it.method_type.contains("BANK", ignoreCase = true)
                        }
                        
                        if (bankMethod != null) {
                            Text(stringResource(R.string.bank_transfer_details), color = Color.Black, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            Spacer(modifier = Modifier.height(16.dp))
                            
                            BankDetailRow("Bank Name", bankMethod.bank_name ?: "N/A", context)
                            BankDetailRow("Account Name", bankMethod.account_name ?: "N/A", context)
                            BankDetailRow("Account Number", bankMethod.account_number ?: "N/A", context)
                            BankDetailRow("IFSC Code", bankMethod.ifsc_code ?: "N/A", context)
                        } else {
                            Text(stringResource(R.string.bank_details_unavailable), color = Color.Red)
                        }
                    } else {
                        // UPI QR
                        val qrMethod = viewModel.paymentMethods.firstOrNull { 
                            (it.method_type == "QR" || it.name.contains("QR", ignoreCase = true) || it.method_type == "UPI") && it.qr_image != null
                        }
                        
                        if (qrMethod?.qr_image != null) {
                            AsyncImage(
                                model = qrMethod.qr_image,
                                contentDescription = "Payment QR Code",
                                modifier = Modifier.size(250.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            // Try to find ANY method with a QR code if specific QR/UPI type not found
                            val anyQrMethod = viewModel.paymentMethods.firstOrNull { it.qr_image != null }
                            if (anyQrMethod?.qr_image != null) {
                                AsyncImage(
                                    model = anyQrMethod.qr_image,
                                    contentDescription = "Payment QR Code",
                                    modifier = Modifier.size(250.dp),
                                    contentScale = ContentScale.Fit
                                )
                            } else {
                                Icon(
                                    Icons.Default.QrCode2,
                                    contentDescription = "QR Code",
                                    modifier = Modifier.size(150.dp),
                                    tint = Color.Black
                                )
                            }
                        }
                    }
                }
            }

            if (!paymentMethod.contains("BANK", ignoreCase = true)) {
                Spacer(modifier = Modifier.height(16.dp))

                val currentQrUrl = if (isUsdt) {
                    val network = if (paymentMethod.contains("TRC20", ignoreCase = true)) "TRC20" else "BEP20"
                    viewModel.paymentMethods.firstOrNull { 
                        it.method_type.contains("USDT", ignoreCase = true) && it.method_type.contains(network, ignoreCase = true)
                    }?.qr_image
                } else {
                    viewModel.paymentMethods.firstOrNull { 
                        (it.method_type == "QR" || it.name.contains("QR", ignoreCase = true) || it.method_type == "UPI") && it.qr_image != null
                    }?.qr_image ?: viewModel.paymentMethods.firstOrNull { it.qr_image != null }?.qr_image
                }

                Button(
                    onClick = { 
                        currentQrUrl?.let { saveImageToGallery(it) }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3F51B5)),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.width(120.dp),
                    enabled = currentQrUrl != null
                ) {
                    Text(stringResource(R.string.save), color = Color.White)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Payment Methods Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                shape = RoundedCornerShape(12.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        "Choose a payment method to pay",
                        color = Color.Black,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )

                    val activeMethods = viewModel.paymentMethods.filter { method ->
                        if (!method.is_active) return@filter false
                        
                        // Filter out the method named "QR" from the list of selectable payment methods
                        if (method.method_type == "QR" || method.name.equals("QR", ignoreCase = true)) return@filter false

                        val category = paymentMethod.lowercase()
                        when {
                            category.contains("usdt") -> {
                                method.method_type.contains("USDT", ignoreCase = true)
                            }
                            category.contains("bank") -> {
                                method.method_type.contains("BANK", ignoreCase = true)
                            }
                            category.contains("upi") -> {
                                method.method_type.contains("UPI", ignoreCase = true) || 
                                method.method_type.contains("QR", ignoreCase = true) ||
                                method.method_type.contains("PAYTM", ignoreCase = true) ||
                                method.method_type.contains("PHONEPE", ignoreCase = true) ||
                                method.method_type.contains("GPAY", ignoreCase = true)
                            }
                            else -> true // Fallback to show all if category unknown
                        }
                    }
                    
                    if (activeMethods.isEmpty()) {
                        Text(
                            "No payment methods available",
                            color = Color.Gray,
                            modifier = Modifier.padding(8.dp),
                            style = androidx.compose.ui.text.TextStyle(fontSize = 14.sp)
                        )
                    } else {
                        // Sort so preferred ones are on top if needed, or keeping backend order
                        activeMethods.forEach { method ->
                            PaymentMethodItem(
                                name = method.name,
                                isSelected = selectedMethod == method.name,
                                onClick = { 
                                    selectedMethod = method.name
                                    // Identify package based on name (with improved matching)
                                    val packageName = getPaymentPackage(method.name)
                                    // Use specific UPI ID if available
                                    if (!method.upi_id.isNullOrBlank()) {
                                        // Debug: Log the method name and detected package
                                        android.util.Log.d("PaymentScreen", "Method: ${method.name}, Package: $packageName, UPI ID: ${method.upi_id}")
                                        openUpiApp(packageName, method.upi_id)
                                    } else {
                                        // Fallback for non-UPI or if UPI ID missing
                                        // If it's a Bank method, maybe show a toast or dialog with details
                                        if (method.method_type == "BANK") {
                                            Toast.makeText(context, "Please use Bank Transfer details", Toast.LENGTH_SHORT).show()
                                        } else {
                                            Toast.makeText(context, "No UPI ID for this method", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                }
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Screenshot Section
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "Paid? Upload Payment Screenshot",
                    color = Color.Black,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(4.dp))
                Icon(
                    Icons.Default.HelpOutline,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = Color(0xFF3F51B5)
                )
                Text(
                    "Guide",
                    color = Color(0xFF3F51B5),
                    fontSize = 14.sp,
                    modifier = Modifier.padding(start = 2.dp)
                )
            }
            Text(
                "Max file size: 10MB. Supported formats: JPG, PNG",
                color = Color.Gray,
                fontSize = 12.sp,
                modifier = Modifier.padding(top = 4.dp)
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Image Picker Area
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .border(1.dp, Color.LightGray, RoundedCornerShape(8.dp))
                    .clickable { launcher.launch("image/*") },
                color = Color.White
            ) {
                if (selectedImageUri != null) {
                    AsyncImage(
                        model = selectedImageUri,
                        contentDescription = "Payment Screenshot",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Fit
                    )
                } else {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(
                            Icons.Default.AddPhotoAlternate,
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = Color.Gray
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(stringResource(R.string.select_payment_screenshot), color = Color.Gray)
                    }
                }
            }

            if (selectedImageUri != null) {
                TextButton(
                    onClick = { selectedImageUri = null },
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text(stringResource(R.string.clear), color = Color.Red)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = { 
                    selectedImageUri?.let { uri ->
                        viewModel.uploadDepositProof(amount, uri, context, onSubmitSuccess)
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3F51B5)),
                shape = RoundedCornerShape(8.dp),
                enabled = !viewModel.isLoading && selectedImageUri != null
            ) {
                if (viewModel.isLoading) {
                    CircularProgressIndicator(color = Color.White, modifier = Modifier.size(24.dp))
                } else {
                    Text(stringResource(R.string.submit_payment_proof), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                }
            }
            
            if (viewModel.errorMessage != null) {
                Text(
                    viewModel.errorMessage!!,
                    color = Color.Red,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}

@Composable
fun PaymentMethodItem(
    name: String,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val iconRes = when {
        name.contains("PhonePe", ignoreCase = true) -> R.drawable.ic_phonepe_custom
        name.contains("Google", ignoreCase = true) || name.contains("GPay", ignoreCase = true) -> R.drawable.ic_gpay_custom
        name.contains("Paytm", ignoreCase = true) -> R.drawable.ic_paytm_custom
        name.contains("UPI", ignoreCase = true) -> R.drawable.ic_upi
        name.contains("USDT", ignoreCase = true) -> R.drawable.ic_usdt
        name.contains("BANK", ignoreCase = true) -> R.drawable.ic_bank
        else -> null
    }

    Surface(
        onClick = onClick,
        color = if (isSelected) Color(0xFFF0F2FF) else Color(0xFFFAFAFA),
        shape = RoundedCornerShape(8.dp),
        border = if (isSelected) BorderStroke(1.dp, Color(0xFF3F51B5)) else null,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (iconRes != null) {
                Image(
                    painter = painterResource(id = iconRes),
                    contentDescription = name,
                    modifier = Modifier.size(32.dp).clip(RoundedCornerShape(4.dp)),
                    contentScale = ContentScale.Fit
                )
            } else {
                val icon = getPaymentIcon(name)
                val iconColor = when {
                    name.contains("Paytm", ignoreCase = true) -> Color(0xFF00BAF2)
                    name.contains("PhonePe", ignoreCase = true) -> Color(0xFF5F259F)
                    name.contains("Google", ignoreCase = true) -> Color(0xFF4285F4)
                    else -> Color.Gray
                }
                Icon(icon, null, tint = iconColor, modifier = Modifier.size(24.dp))
            }
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                name,
                color = Color.Black,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f)
            )
            Icon(
                Icons.Default.TouchApp,
                contentDescription = null,
                tint = Color(0xFF3F51B5),
                modifier = Modifier.size(24.dp)
            )
        }
    }
}

// Helpers
private fun getPaymentIcon(name: String): ImageVector {
    return when {
        name.contains("Paytm", ignoreCase = true) -> Icons.Default.Payments
        name.contains("PhonePe", ignoreCase = true) -> Icons.Default.AccountBalanceWallet
        name.contains("Google", ignoreCase = true) -> Icons.Default.AccountBalance
        name.contains("Bhim", ignoreCase = true) -> Icons.Default.QrCode
        else -> Icons.Default.Payment
    }
}

private fun getPaymentPackage(name: String): String? {
    val lowerName = name.lowercase().replace(" ", "").replace("-", "").replace("_", "")
    return when {
        lowerName.contains("paytm") -> "net.one97.paytm"
        lowerName.contains("phonepe") || lowerName.contains("phone") -> "com.phonepe.app"
        lowerName.contains("google") || lowerName.contains("gpay") -> "com.google.android.apps.nbu.paisa.user"
        lowerName.contains("bhim") -> "in.org.npci.upiapp"
        else -> null 
    }
}

private fun getAppName(packageName: String?): String {
    return when (packageName) {
        "com.phonepe.app" -> "PhonePe"
        "com.google.android.apps.nbu.paisa.user" -> "Google Pay"
        "net.one97.paytm" -> "Paytm"
        else -> "payment app"
    }
}

@Composable
fun BankDetailRow(label: String, value: String, context: android.content.Context) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, color = Color.Gray, fontSize = 12.sp)
            SelectionContainer {
                Text(value, color = Color.Black, fontSize = 16.sp, fontWeight = FontWeight.Medium)
            }
        }
        IconButton(
            onClick = {
                val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                val clip = android.content.ClipData.newPlainText(label, value)
                clipboard.setPrimaryClip(clip)
                Toast.makeText(context, "$label copied", Toast.LENGTH_SHORT).show()
            }
        ) {
            Icon(Icons.Default.ContentCopy, contentDescription = "Copy", modifier = Modifier.size(20.dp), tint = Color(0xFF3F51B5))
        }
    }
}
