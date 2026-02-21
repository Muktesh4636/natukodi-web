package com.sikwin.app.ui.screens

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.LocalContext
import android.widget.Toast
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*

import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DepositScreen(
    viewModel: GunduAtaViewModel,
    initialMethod: String? = null,
    onBack: () -> Unit,
    onNavigateToWithdraw: () -> Unit,
    onNavigateToPayment: (String, String) -> Unit
) {
    var amount by remember { mutableStateOf(if (initialMethod == "USDT") "500" else "200") }
    var selectedMethod by remember { mutableStateOf(if (initialMethod == "USDT") "USDT" else "UPI") } // "Bank", "UPI", or "USDT"
    var selectedOption by remember { mutableStateOf(if (initialMethod == "USDT") "usdt_trc20" else "upi") }
    
    val focusManager = LocalFocusManager.current
    var isAmountFocused by remember { mutableStateOf(false) }
    var hasBeenFocused by remember { mutableStateOf(false) }

    val usdtExchangeRate = 95
    val usdtMinDeposit = 500
    val normalMinDeposit = 200
    val usdtBonusPercent = 0.05

    val currentMinDeposit = if (selectedMethod == "USDT") usdtMinDeposit else normalMinDeposit
    val isAmountValid = amount.isNotBlank() && (amount.toIntOrNull() ?: 0) >= currentMinDeposit

    val usdtAmount = if (selectedMethod == "USDT" && amount.isNotBlank()) {
        try {
            amount.toDouble() / usdtExchangeRate
        } catch (e: Exception) {
            0.0
        }
    } else 0.0

    val bonusAmount = if (selectedMethod == "USDT" && amount.isNotBlank()) {
        try {
            amount.toDouble() * usdtBonusPercent
        } catch (e: Exception) {
            0.0
        }
    } else 0.0

    val context = LocalContext.current

    LaunchedEffect(Unit) {
        viewModel.fetchWallet()
        viewModel.clearError()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null
            ) { 
                focusManager.clearFocus() 
            }
            .verticalScroll(rememberScrollState())
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Default.ArrowBack, null, tint = PrimaryYellow, modifier = Modifier.size(32.dp))
            }
            Text(
                "Deposit",
                color = PrimaryYellow,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f).padding(end = 48.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )
        }


        // Payment Method
        Column(modifier = Modifier.padding(16.dp)) {
            Text(stringResource(R.string.payment_method), color = TextGrey, fontSize = 16.sp)
            
            Row(modifier = Modifier.padding(vertical = 12.dp)) {
                PaymentTab("Bank", selectedMethod == "Bank") { 
                    selectedMethod = "Bank"
                    selectedOption = "bank"
                    if (amount.isBlank() || (amount.toIntOrNull() ?: 0) < normalMinDeposit) {
                        amount = normalMinDeposit.toString()
                    }
                }
                Spacer(modifier = Modifier.width(16.dp))
                PaymentTab("UPI", selectedMethod == "UPI") { 
                    selectedMethod = "UPI"
                    selectedOption = "upi"
                    if (amount.isBlank() || (amount.toIntOrNull() ?: 0) < normalMinDeposit) {
                        amount = normalMinDeposit.toString()
                    }
                }
                Spacer(modifier = Modifier.width(16.dp))
                PaymentTab("USDT", selectedMethod == "USDT") { 
                    selectedMethod = "USDT"
                    selectedOption = "usdt_trc20"
                    if (amount.isBlank() || (amount.toIntOrNull() ?: 0) < usdtMinDeposit) {
                        amount = usdtMinDeposit.toString()
                    }
                }
            }

            // Payment Options Grid
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                when (selectedMethod) {
                    "UPI" -> {
                        PaymentOptionCard("upi", selectedOption == "upi") { selectedOption = "upi" }
                    }
                    "Bank" -> {
                        PaymentOptionCard("BANK", selectedOption == "bank") { selectedOption = "bank" }
                    }
                    "USDT" -> {
                        PaymentOptionCard("USDT (TRC20)", selectedOption == "usdt_trc20") { selectedOption = "usdt_trc20" }
                        PaymentOptionCard("USDT (BEP20)", selectedOption == "usdt_bep20") { selectedOption = "usdt_bep20" }
                    }
                }
            }
        }

        Divider(color = BorderColor, thickness = 8.dp)

        // Deposit Amount
        Column(modifier = Modifier.padding(16.dp)) {
            Text(stringResource(R.string.deposit_amount), color = TextGrey, fontSize = 16.sp)
            
            Text(
                "Deposit ₹2000 or more to get a FREE MEGA SPIN!",
                color = PrimaryYellow,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(vertical = 8.dp)
            )
            
            if (selectedMethod == "USDT") {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    color = PrimaryYellow.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, PrimaryYellow)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(stringResource(R.string.usdt_deposit_info), color = PrimaryYellow, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text("• ${stringResource(R.string.exchange_rate, usdtExchangeRate.toString())}", color = TextWhite, fontSize = 13.sp)
                        Text("• ${stringResource(R.string.min_deposit, usdtMinDeposit.toString())}", color = TextWhite, fontSize = 13.sp)
                        Text("• ${stringResource(R.string.bonus_cashback)}", color = GreenSuccess, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }
            } else {
                Text(
                    "Enter the amount and click confirm, the payment information will be displayed.",
                    color = Color.Red,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }
            
            OutlinedTextField(
                value = amount,
                onValueChange = { newValue ->
                    // Filter to allow only digits
                    amount = newValue.filter { it.isDigit() }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .onFocusChanged { focusState ->
                        isAmountFocused = focusState.isFocused
                        if (focusState.isFocused) hasBeenFocused = true
                    },
                placeholder = { Text(stringResource(R.string.enter_deposit_amount), color = TextGrey) },
                leadingIcon = { Text("₹", color = TextGrey, fontSize = 20.sp, modifier = Modifier.padding(start = 12.dp)) },
                suffix = {
                    if (selectedMethod == "USDT" && usdtAmount > 0) {
                        Text("≈ ${String.format("%.2f", usdtAmount)} USDT", color = PrimaryYellow, fontSize = 14.sp)
                    }
                },
                isError = !isAmountValid && !isAmountFocused && hasBeenFocused,
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = BorderColor,
                focusedBorderColor = PrimaryYellow,
                errorBorderColor = Color.Red,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
                shape = RoundedCornerShape(8.dp),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )

            if (!isAmountValid && !isAmountFocused && hasBeenFocused) {
                Text(
                    text = stringResource(R.string.min_deposit_toast, currentMinDeposit.toString()),
                    color = Color.Red,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 4.dp, start = 4.dp)
                )
            }

            if (selectedMethod == "USDT" && bonusAmount > 0) {
                Text(
                    "You will receive extra ₹${String.format("%.2f", bonusAmount)} cashback!",
                    color = GreenSuccess,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            Spacer(modifier = Modifier.height(12.dp))
            
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.current_success_rate), color = TextGrey, fontSize = 14.sp)
                Surface(
                    color = GreenSuccess,
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        "High",
                        color = TextWhite,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            Button(
                onClick = { 
                    if (isAmountValid) {
                        onNavigateToPayment(amount, selectedOption)
                    } else {
                        Toast.makeText(context, "Minimum deposit ₹$currentMinDeposit", Toast.LENGTH_SHORT).show()
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = PrimaryYellow
                ),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(stringResource(R.string.submit), color = BlackBackground, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            Text(stringResource(R.string.reminder), color = Color.Red, fontWeight = FontWeight.Bold)
            Text(
                stringResource(R.string.deposit_reminder),
                color = TextGrey,
                fontSize = 13.sp,
                lineHeight = 18.sp
            )
        }
    }
}

@Composable
fun PaymentTab(text: String, isSelected: Boolean, onClick: () -> Unit) {
    Column(
        modifier = Modifier.clickable { onClick() },
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = text,
            color = if (isSelected) PrimaryYellow else TextGrey,
            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
            fontSize = 16.sp
        )
        if (isSelected) {
            Box(
                modifier = Modifier
                    .width(40.dp)
                    .height(2.dp)
                    .background(PrimaryYellow)
                    .padding(top = 4.dp)
            )
        }
    }
}

@Composable
fun PaymentOptionCard(text: String, isSelected: Boolean, onClick: () -> Unit) {
    val iconRes = when {
        text.contains("UPI", ignoreCase = true) -> R.drawable.ic_upi
        text.contains("BANK", ignoreCase = true) -> R.drawable.ic_bank
        text.contains("USDT", ignoreCase = true) -> R.drawable.ic_usdt
        else -> null
    }

    Box(
        modifier = Modifier
            .width(120.dp)
            .height(80.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(SurfaceColor)
            .border(
                width = 1.dp,
                color = if (isSelected) PrimaryYellow else BorderColor,
                shape = RoundedCornerShape(8.dp)
            )
            .clickable { onClick() }
            .padding(8.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            // Payment Icon
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .background(Color.White, RoundedCornerShape(4.dp)),
                contentAlignment = Alignment.Center
            ) {
                if (iconRes != null) {
                    Image(
                        painter = painterResource(id = iconRes),
                        contentDescription = text,
                        modifier = Modifier.size(24.dp)
                    )
                } else {
                    Icon(
                        imageVector = Icons.Default.Payment,
                        contentDescription = text,
                        tint = Color(0xFF6C3FB5),
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(text, color = TextWhite, fontSize = 10.sp)
        }
    }
}
