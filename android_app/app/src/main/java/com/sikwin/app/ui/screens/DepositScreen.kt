package com.sikwin.app.ui.screens

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
import com.sikwin.app.ui.theme.*

import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DepositScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onNavigateToWithdraw: () -> Unit,
    onNavigateToPayment: (String) -> Unit
) {
    var amount by remember { mutableStateOf("") }
    var selectedMethod by remember { mutableStateOf("UPI") } // "Bank" or "UPI"
    var selectedOption by remember { mutableStateOf("upi(200-10k)") }

    LaunchedEffect(Unit) {
        viewModel.fetchWallet()
        viewModel.clearError()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
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

        // Balance Section
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Balance", color = TextGrey, fontSize = 18.sp)
                Spacer(modifier = Modifier.width(8.dp))
                IconButton(onClick = { viewModel.fetchWallet() }) {
                    Icon(Icons.Default.Refresh, null, tint = TextWhite, modifier = Modifier.size(20.dp))
                }
            }
            Text("₹ ${viewModel.wallet?.balance ?: "0.00"}", color = PrimaryYellow, fontSize = 28.sp, fontWeight = FontWeight.Bold)
            
            Spacer(modifier = Modifier.height(16.dp))
            
            OutlinedButton(
                onClick = onNavigateToWithdraw,
                border = BorderStroke(1.dp, PrimaryYellow),
                shape = RoundedCornerShape(20.dp)
            ) {
                Text("Withdrawal", color = PrimaryYellow)
            }
        }

        Divider(color = BorderColor, thickness = 8.dp)

        // Payment Method
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Payment method", color = TextGrey, fontSize = 16.sp)
            
            Row(modifier = Modifier.padding(vertical = 12.dp)) {
                PaymentTab("Bank", selectedMethod == "Bank") { selectedMethod = "Bank" }
                Spacer(modifier = Modifier.width(16.dp))
                PaymentTab("UPI", selectedMethod == "UPI") { selectedMethod = "UPI" }
            }

            // Payment Options Grid
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                if (selectedMethod == "UPI") {
                    PaymentOptionCard("upi (200-10k)", selectedOption == "upi(200-10k)") { selectedOption = "upi(200-10k)" }
                } else {
                    PaymentOptionCard("BANK(200-200k)", selectedOption == "bank") { selectedOption = "bank" }
                }
            }
        }

        Divider(color = BorderColor, thickness = 8.dp)

        // Deposit Amount
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Deposit amount", color = TextGrey, fontSize = 16.sp)
            Text(
                "Enter the amount and click confirm, the payment information will be displayed.",
                color = Color.Red,
                fontSize = 12.sp,
                modifier = Modifier.padding(vertical = 8.dp)
            )
            
            OutlinedTextField(
                value = amount,
                onValueChange = { newValue ->
                    // Filter to allow only digits, automatically converting decimals to floor value
                    val filtered = newValue.filter { it.isDigit() || it == '.' }
                    // If there's a decimal point, take only the integer part (floor value)
                    amount = if (filtered.contains('.')) {
                        filtered.substringBefore('.')
                    } else {
                        filtered
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Please enter the deposit amount", color = TextGrey) },
                leadingIcon = { Text("₹", color = TextGrey, fontSize = 20.sp, modifier = Modifier.padding(start = 12.dp)) },
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = BorderColor,
                focusedBorderColor = PrimaryYellow,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
                shape = RoundedCornerShape(8.dp),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )

            Spacer(modifier = Modifier.height(12.dp))
            
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Current success deposit rate : ", color = TextGrey, fontSize = 14.sp)
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
                    if (amount.isNotBlank()) {
                        onNavigateToPayment(amount)
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text("Submit", color = BlackBackground, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            Text("Reminder:", color = Color.Red, fontWeight = FontWeight.Bold)
            Text(
                "Kindly refrain from saving previously used bank account details for your payments, as the receiving bank account changes frequently. Once a deposit is made to a frozen account, we cannot be held accountable for any resulting issues.",
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
            // UPI Icon
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .background(Color.White, RoundedCornerShape(4.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Payment,
                    contentDescription = "UPI",
                    tint = Color(0xFF6C3FB5),
                    modifier = Modifier.size(20.dp)
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(text, color = TextWhite, fontSize = 10.sp)
        }
    }
}
