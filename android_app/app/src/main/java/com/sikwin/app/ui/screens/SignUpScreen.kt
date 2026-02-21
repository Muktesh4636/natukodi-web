package com.sikwin.app.ui.screens

import androidx.compose.ui.graphics.Brush
import androidx.compose.animation.core.*
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*

import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.core.content.ContextCompat

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SignUpScreen(
    viewModel: GunduAtaViewModel,
    initialReferralCode: String = "",
    initialSpinBalance: Int = 0,
    onSignUpSuccess: () -> Unit,
    onNavigateToSignIn: () -> Unit,
    onNavigateToLuckyWheel: () -> Unit = {}
) {
    val context = LocalContext.current
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var phoneNumber by remember { mutableStateOf("") }
    var otpCode by remember { mutableStateOf("") }
    var referralCode by remember { mutableStateOf(initialReferralCode) }
    var spinBalance by remember { mutableIntStateOf(initialSpinBalance) }
    var passwordVisible by remember { mutableStateOf(false) }
    var timerSeconds by remember { mutableIntStateOf(0) }
    var showReferralInput by remember { mutableStateOf(false) }

    // Timer logic
    LaunchedEffect(timerSeconds) {
        if (timerSeconds > 0) {
            kotlinx.coroutines.delay(1000)
            timerSeconds -= 1
        }
    }

    LaunchedEffect(viewModel.loginSuccess) {
        if (viewModel.loginSuccess) {
            // Mark as new user to trigger spin wheel on home screen
            viewModel.markUserAsNew()
            onSignUpSuccess()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (viewModel.isLoading) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = PrimaryYellow)
        }
        
        viewModel.errorMessage?.let {
            Text(it, color = RedError, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp))
        }

        Row(modifier = Modifier.fillMaxWidth()) {
            IconButton(onClick = onNavigateToSignIn) {
                Icon(Icons.Default.ArrowBack, null, tint = TextWhite)
            }
        }
        
        Spacer(modifier = Modifier.height(20.dp))
        
        val infiniteTransition = rememberInfiniteTransition(label = "shimmerEffect")
        val shimmerOffset by infiniteTransition.animateFloat(
            initialValue = 0f,
            targetValue = 1000f,
            animationSpec = infiniteRepeatable(
                animation = tween(2000, easing = LinearEasing),
                repeatMode = RepeatMode.Restart
            ),
            label = "shimmerOffset"
        )

        val shimmerBrush = Brush.linearGradient(
            colors = listOf(
                PrimaryYellow,
                Color.White,
                PrimaryYellow
            ),
            start = androidx.compose.ui.geometry.Offset(shimmerOffset - 300f, shimmerOffset - 300f),
            end = androidx.compose.ui.geometry.Offset(shimmerOffset, shimmerOffset)
        )

        Column(modifier = Modifier.align(Alignment.Start)) {
            Text(
                text = stringResource(R.string.sign_up_title),
                style = MaterialTheme.typography.headlineLarge.copy(
                    brush = shimmerBrush
                ),
                fontWeight = FontWeight.ExtraBold
            )
            Text(
                text = stringResource(R.string.welcome_to_gundu_ata),
                style = MaterialTheme.typography.bodyMedium,
                color = TextGrey
            )
        }
        
        Spacer(modifier = Modifier.height(40.dp))

        // Username
        InputFieldLabel("Username")
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text(stringResource(R.string.enter_username), color = TextGrey) },
            leadingIcon = { Icon(Icons.Default.Person, null, tint = TextGrey) },
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = BorderColor,
                focusedBorderColor = PrimaryYellow,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
            shape = RoundedCornerShape(8.dp),
            singleLine = true
        )

        Spacer(modifier = Modifier.height(20.dp))

        // Password
        InputFieldLabel("Password")
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text(stringResource(R.string.enter_password), color = TextGrey) },
            leadingIcon = { Icon(Icons.Default.Lock, null, tint = TextGrey) },
            trailingIcon = {
                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                    Icon(
                        imageVector = if (passwordVisible) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                        null,
                        tint = TextGrey
                    )
                }
            },
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = BorderColor,
                focusedBorderColor = PrimaryYellow,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
            shape = RoundedCornerShape(8.dp),
            singleLine = true,
            visualTransformation = if (passwordVisible) androidx.compose.ui.text.input.VisualTransformation.None else androidx.compose.ui.text.input.PasswordVisualTransformation()
        )

        Spacer(modifier = Modifier.height(20.dp))

        // Phone Number
        InputFieldLabel("Phone number")
        OutlinedTextField(
            value = phoneNumber,
            onValueChange = { phoneNumber = it },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text(stringResource(R.string.enter_phone_number), color = TextGrey) },
            leadingIcon = { Text("+91", color = TextWhite, modifier = Modifier.padding(start = 12.dp)) },
            colors = TextFieldDefaults.outlinedTextFieldColors(
                containerColor = SurfaceColor,
                unfocusedBorderColor = BorderColor,
                focusedBorderColor = PrimaryYellow,
                focusedTextColor = TextWhite,
                unfocusedTextColor = TextWhite
            ),
            shape = RoundedCornerShape(8.dp),
            singleLine = true,
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone)
        )

        Spacer(modifier = Modifier.height(20.dp))

        // OTP Code
        InputFieldLabel("OTP Code")
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = otpCode,
                onValueChange = { otpCode = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text(stringResource(R.string.enter_otp), color = TextGrey) },
                leadingIcon = { Icon(Icons.Default.Lock, null, tint = TextGrey) },
                colors = TextFieldDefaults.outlinedTextFieldColors(
                    containerColor = SurfaceColor,
                    unfocusedBorderColor = BorderColor,
                    focusedBorderColor = PrimaryYellow,
                    focusedTextColor = TextWhite,
                    unfocusedTextColor = TextWhite
                ),
                shape = RoundedCornerShape(8.dp),
                singleLine = true,
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number)
            )
            
            Spacer(modifier = Modifier.width(8.dp))
            
            Button(
                onClick = { 
                    viewModel.sendOtp(phoneNumber)
                    timerSeconds = 10
                },
                enabled = !viewModel.isLoading && phoneNumber.length >= 10 && timerSeconds == 0,
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.height(56.dp)
            ) {
                Text(
                    if (timerSeconds > 0) "Resend in ${timerSeconds}s" 
                    else if (viewModel.otpSent) "Resend" 
                    else "Get OTP", 
                    color = BlackBackground, 
                    fontSize = 12.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Referral Code Toggle
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { showReferralInput = !showReferralInput }
                .padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (showReferralInput) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                contentDescription = null,
                tint = PrimaryYellow
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = stringResource(R.string.have_referral_code),
                color = PrimaryYellow,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold
            )
        }

        if (showReferralInput) {
            Spacer(modifier = Modifier.height(8.dp))
            // Referral Code
            OutlinedTextField(
                value = referralCode,
                onValueChange = { referralCode = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text(stringResource(R.string.enter_referral_code), color = TextGrey) },
                leadingIcon = { Icon(Icons.Default.GroupAdd, null, tint = TextGrey) },
                colors = TextFieldDefaults.outlinedTextFieldColors(
                    containerColor = SurfaceColor,
                    unfocusedBorderColor = BorderColor,
                    focusedBorderColor = PrimaryYellow,
                    focusedTextColor = TextWhite,
                    unfocusedTextColor = TextWhite
                ),
                shape = RoundedCornerShape(8.dp),
                singleLine = true
            )
        }

        Spacer(modifier = Modifier.height(40.dp))

        Button(
            onClick = { 
                // Trim and clean OTP code before sending
                val cleanOtpCode = otpCode.trim().replace(" ", "").replace("-", "")
                val registrationData = mutableMapOf(
                    "username" to username.trim(),
                    "password" to password,
                    "password2" to password,
                    "phone_number" to phoneNumber.trim(),
                    "otp_code" to cleanOtpCode
                )
                if (referralCode.isNotBlank()) {
                    registrationData["referral_code"] = referralCode.trim()
                }
                if (spinBalance > 0) {
                    registrationData["spin_balance"] = spinBalance.toString()
                }
                viewModel.register(registrationData)
            },
            enabled = !viewModel.isLoading && username.isNotBlank() && password.isNotBlank() && phoneNumber.isNotBlank() && (!viewModel.otpSent || otpCode.isNotBlank()),
            modifier = Modifier.fillMaxWidth().height(56.dp),
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
            shape = RoundedCornerShape(8.dp)
        ) {
            Text(stringResource(R.string.sign_up), color = BlackBackground, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }

        Spacer(modifier = Modifier.height(24.dp))

        OutlinedButton(
            onClick = onNavigateToSignIn,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            border = BorderStroke(1.dp, PrimaryYellow),
            shape = RoundedCornerShape(8.dp)
        ) {
            Text(stringResource(R.string.sign_in), color = PrimaryYellow, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }
    }
}

@Composable
fun InputFieldLabel(text: String) {
    Text(
        text = text,
        color = TextWhite,
        fontSize = 14.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
    )
}
