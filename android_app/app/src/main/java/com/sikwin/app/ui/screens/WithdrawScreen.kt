package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WithdrawScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onAddBankAccount: () -> Unit
) {
    LaunchedEffect(Unit) {
        viewModel.fetchBankDetails()
        viewModel.fetchWallet()
    }

    val bankAccounts = viewModel.bankDetails
    
    var amount by remember { mutableStateOf("") }
    var selectedBank by remember { mutableStateOf(bankAccounts.firstOrNull()) }
    var showBankDropdown by remember { mutableStateOf(false) }

    // Update selected bank when bankAccounts are loaded
    LaunchedEffect(bankAccounts) {
        if (selectedBank == null && bankAccounts.isNotEmpty()) {
            selectedBank = bankAccounts.firstOrNull { it.is_default } ?: bankAccounts.first()
        }
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
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = PrimaryYellow,
                    modifier = Modifier.size(24.dp)
                )
            }
            Text(
                "Online withdrawal",
                color = PrimaryYellow,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.width(48.dp))
        }

        // Tabs
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                "Bank Account",
                color = PrimaryYellow,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(vertical = 12.dp)
            )
            Box(
                modifier = Modifier
                    .width(60.dp)
                    .height(3.dp)
                    .background(PrimaryYellow)
            )
        }

        Divider(color = BorderColor, thickness = 1.dp)

        Spacer(modifier = Modifier.height(16.dp))

        // Wallet Balance Info
        viewModel.wallet?.let { wallet ->
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .background(SurfaceColor, RoundedCornerShape(8.dp))
                    .padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Available Balance", color = TextGrey, fontSize = 12.sp)
                        Text("₹${wallet.balance}", color = PrimaryYellow, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Unavailable Balance", color = TextGrey, fontSize = 12.sp)
                        Text("₹${wallet.unavaliable_balance}", color = Color.Gray, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))


        if (bankAccounts.isEmpty()) {
            // No Bank account added
            Text(
                "No Bank account added, add bank account",
                color = PrimaryYellow,
                fontSize = 14.sp,
                textDecoration = TextDecoration.Underline,
                modifier = Modifier
                    .padding(horizontal = 16.dp)
                    .clickable { onAddBankAccount() }
            )
        } else {
            // Bank account selected
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Bank Selector
                Box(modifier = Modifier.fillMaxWidth()) {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showBankDropdown = true },
                        color = BlackBackground,
                        border = androidx.compose.foundation.BorderStroke(1.dp, BorderColor),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = selectedBank?.let { "${it.bank_name}(${it.account_number.takeLast(4)})" } ?: "Select Bank Account",
                                color = TextWhite,
                                fontSize = 16.sp
                            )
                            Icon(Icons.Default.ArrowDropDown, null, tint = TextGrey)
                        }
                    }
                    
                    DropdownMenu(
                        expanded = showBankDropdown,
                        onDismissRequest = { showBankDropdown = false },
                        modifier = Modifier.fillMaxWidth(0.9f).background(SurfaceColor)
                    ) {
                        bankAccounts.forEach { bank ->
                            DropdownMenuItem(
                                text = { Text("${bank.bank_name}(${bank.account_number.takeLast(4)})", color = TextWhite) },
                                onClick = {
                                    selectedBank = bank
                                    showBankDropdown = false
                                }
                            )
                        }
                        Divider(color = BorderColor)
                        DropdownMenuItem(
                            text = { Text("+ Add bank account", color = PrimaryYellow) },
                            onClick = {
                                showBankDropdown = false
                                onAddBankAccount()
                            }
                        )
                    }
                }

                // Amount Input
                OutlinedTextField(
                    value = amount,
                    onValueChange = { newValue ->
                    amount = newValue.filter { it.isDigit() }
                },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Please enter amount", color = TextGrey) },
                    leadingIcon = { Text("₹", color = TextWhite, fontSize = 18.sp, modifier = Modifier.padding(start = 12.dp)) },
                    colors = TextFieldDefaults.outlinedTextFieldColors(
                        containerColor = BlackBackground,
                        unfocusedBorderColor = BorderColor,
                        focusedBorderColor = PrimaryYellow,
                        focusedTextColor = TextWhite,
                        unfocusedTextColor = TextWhite
                    ),
                    shape = RoundedCornerShape(4.dp),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )


                Spacer(modifier = Modifier.height(8.dp))

                // Error Message
                viewModel.errorMessage?.let { error ->
                    Text(
                        text = error,
                        color = Color.Red,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)
                    )
                }

                // Submit Button
                Button(
                    onClick = { 
                        if (amount.isNotBlank() && selectedBank != null) {
                            viewModel.initiateWithdraw(amount, selectedBank!!) {
                                // On Success, maybe show a toast or navigate back
                                onBack() 
                            }
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    enabled = !viewModel.isLoading,
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    if (viewModel.isLoading) {
                        CircularProgressIndicator(color = BlackBackground, modifier = Modifier.size(24.dp))
                    } else {
                        Text(
                            "Submit",
                            color = BlackBackground,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}

