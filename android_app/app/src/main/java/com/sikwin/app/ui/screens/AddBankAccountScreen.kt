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
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddBankAccountScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onSubmitSuccess: () -> Unit
) {
    var accountHolderName by remember { mutableStateOf("") }
    var accountNumber by remember { mutableStateOf("") }
    var bankName by remember { mutableStateOf("") }
    var ifsc by remember { mutableStateOf("") }
    var setAsDefault by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.errorMessage = null
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
                stringResource(R.string.add_bank_account_title),
                color = PrimaryYellow,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.width(48.dp))
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Account holder name
            AddBankField(
                label = stringResource(R.string.account_holder_name),
                value = accountHolderName,
                onValueChange = { accountHolderName = it },
                placeholder = stringResource(R.string.account_holder_placeholder),
                singleLine = true
            )

            // Account Number
            AddBankField(
                label = stringResource(R.string.account_number),
                value = accountNumber,
                onValueChange = { accountNumber = it },
                placeholder = stringResource(R.string.account_number_placeholder),
                keyboardType = KeyboardType.Number,
                singleLine = true
            )

            // Bank name
            AddBankField(
                label = stringResource(R.string.bank_name),
                value = bankName,
                onValueChange = { bankName = it },
                placeholder = stringResource(R.string.bank_name_placeholder),
                singleLine = true
            )

            // IFSC
            AddBankField(
                label = stringResource(R.string.ifsc),
                value = ifsc,
                onValueChange = { ifsc = it },
                placeholder = stringResource(R.string.ifsc_placeholder),
                singleLine = true
            )

            // Error Message
            if (viewModel.errorMessage != null) {
                Text(
                    text = viewModel.errorMessage!!,
                    color = Color.Red,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            // Set as default
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(stringResource(R.string.set_as_default_colon), color = TextWhite, fontSize = 16.sp)
                Switch(
                    checked = setAsDefault,
                    onCheckedChange = { setAsDefault = it },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = Color.White,
                        checkedTrackColor = PrimaryYellow,
                        uncheckedThumbColor = Color.White,
                        uncheckedTrackColor = Color.Gray
                    )
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Submit Button
            Button(
                onClick = { 
                    if (accountHolderName.isBlank() || accountNumber.isNotBlank().not() || bankName.isBlank() || ifsc.isBlank()) {
                        // Show some validation error or just do nothing for now
                        // viewModel.errorMessage = "Please fill all fields"
                        return@Button
                    }
                    val data = mapOf(
                        "account_name" to accountHolderName.trim(),
                        "account_number" to accountNumber.trim(),
                        "bank_name" to bankName.trim(),
                        "ifsc_code" to ifsc.trim(),
                        "is_default" to setAsDefault
                    )
                    viewModel.addBankDetail(data) {
                        onSubmitSuccess()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                enabled = !viewModel.isLoading,
                shape = RoundedCornerShape(8.dp)
            ) {
                if (viewModel.isLoading) {
                    CircularProgressIndicator(color = BlackBackground, modifier = Modifier.size(24.dp))
                } else {
                    Text(
                        stringResource(R.string.submit),
                        color = BlackBackground,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddBankField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = false
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            label,
            color = PrimaryYellow,
            fontSize = 16.sp,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text(placeholder, color = TextGrey, fontSize = 14.sp) },
            singleLine = singleLine,
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = Color.Transparent,
                focusedBorderColor = PrimaryYellow,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
            shape = RoundedCornerShape(4.dp),
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType)
        )
    }
}
