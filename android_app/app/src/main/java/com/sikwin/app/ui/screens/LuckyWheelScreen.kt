package com.sikwin.app.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import com.sikwin.app.R
import com.sikwin.app.ui.theme.BlackBackground
import com.sikwin.app.ui.theme.PrimaryYellow
import com.sikwin.app.ui.theme.SurfaceColor
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import android.media.MediaPlayer
import androidx.compose.runtime.DisposableEffect
import kotlin.random.Random

@Composable
fun LuckyWheelScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var rotationAngle by remember { mutableStateOf(0f) }
    var isSpinning by remember { mutableStateOf(false) }
    var showResultDialog by remember { mutableStateOf(false) }
    var lastResult by remember { mutableStateOf("") }
    var hasClaimedToday by remember { mutableStateOf(false) }
    var claimedAmount by remember { mutableStateOf<String?>(null) }
    
    // MediaPlayer for wheel sound
    val mediaPlayer = remember {
        try {
            MediaPlayer.create(context, R.raw.wheel_sound)?.apply {
                isLooping = false
            }
        } catch (e: Exception) {
            null
        }
    }
    
    DisposableEffect(Unit) {
        onDispose {
            mediaPlayer?.release()
        }
    }
    
    LaunchedEffect(isSpinning) {
        if (isSpinning) {
            mediaPlayer?.let { player ->
                if (player.isPlaying) player.seekTo(0) else player.start()
            }
        }
    }

    LaunchedEffect(Unit) {
        viewModel.checkDailyRewardStatus { claimed, message, amount ->
            hasClaimedToday = claimed
            claimedAmount = amount
            if (claimed && amount != null) {
                lastResult = "₹$amount"
            }
        }
    }

    val wheelItems = listOf(
        WheelItem("₹300", Color(0xFFFF0000)),
        WheelItem("₹100", Color(0xFFFF4500)),
        WheelItem("₹40", Color(0xFFFFA500)),
        WheelItem("₹30", Color(0xFFFFD700)),
        WheelItem("₹20", Color(0xFF32CD32)),
        WheelItem("₹10", Color(0xFF00CED1)),
        WheelItem("₹5", Color(0xFF4169E1)),
        WheelItem("Better luck\nnext time", Color(0xFFC0C0C0))
    )

    fun performSpin() {
        if (!isSpinning && !hasClaimedToday) {
            isSpinning = true
            viewModel.claimDailyReward { success, amount, type, message ->
                if (success) {
                    // hasClaimedToday = true // Move this to the animation finished listener to prevent premature disabling
                    val finalAmount = amount ?: 0
                    val targetIndex = when (finalAmount) {
                        300 -> 0; 100 -> 1; 40 -> 2; 30 -> 3; 20 -> 4; 10 -> 5; 5 -> 6; else -> 7
                    }
                    lastResult = "₹$finalAmount"
                    val extraRotations = 10 + Random.nextInt(5)
                    val degreesPerSegment = 360f / wheelItems.size
                    val targetAngle = 270f - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
                    val currentRotation = rotationAngle % 360
                    var angleDiff = targetAngle - currentRotation
                    if (angleDiff <= 0) angleDiff += 360
                    rotationAngle += (extraRotations * 360) + angleDiff
                    
                    // Refresh wallet balance after successful claim
                    viewModel.fetchWallet()
                } else {
                    isSpinning = false
                    lastResult = message ?: "Failed to claim reward"
                }
            }
        }
    }

    val rotation = animateFloatAsState(
        targetValue = rotationAngle,
        animationSpec = tween(durationMillis = 4000, easing = CubicBezierEasing(0.1f, 0.0f, 0.2f, 1f)),
        label = "wheel_rotation",
        finishedListener = { 
            if (rotationAngle != 0f) { 
                isSpinning = false
                hasClaimedToday = true // Disable only AFTER animation finishes
                showResultDialog = true 
            } 
        }
    )

    if (showResultDialog) {
        AlertDialog(
            onDismissRequest = { showResultDialog = false },
            title = { Text("Result", fontWeight = FontWeight.Bold) },
            text = {
                val message = if (lastResult == "Better luck next time") "Better luck next time! Try again tomorrow." else "Congratulations! You won $lastResult"
                Text(message)
            },
            confirmButton = { TextButton(onClick = { showResultDialog = false }) { Text(stringResource(R.string.ok), color = PrimaryYellow) } },
            containerColor = SurfaceColor,
            titleContentColor = PrimaryYellow,
            textContentColor = Color.White
        )
    }

    Box(modifier = Modifier.fillMaxSize().background(BlackBackground)) {
        Image(painter = painterResource(id = R.drawable.money_decoration), contentDescription = null, modifier = Modifier.fillMaxSize().padding(20.dp), contentScale = ContentScale.Inside, alpha = 0.4f)
        Column(modifier = Modifier.fillMaxSize()) {
            WheelHeader(onBack, viewModel.wallet?.balance ?: "0.00")
            Column(modifier = Modifier.fillMaxSize().padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Text(if (hasClaimedToday) "REWARD CLAIMED!" else "DAILY REWARDS", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(bottom = 32.dp))
                Box(contentAlignment = Alignment.TopCenter, modifier = Modifier.size(360.dp)) {
                    Canvas(modifier = Modifier.size(340.dp).align(Alignment.Center)) { drawCircle(color = PrimaryYellow.copy(alpha = 0.2f), radius = size.minDimension / 2, style = Stroke(width = 20.dp.toPx())) }
                    Box(modifier = Modifier.size(300.dp).align(Alignment.Center)) { WheelCanvas(wheelItems, rotation.value) }
                    Box(modifier = Modifier.padding(top = 10.dp)) { WheelPointer() }
                    Surface(modifier = Modifier.size(60.dp).align(Alignment.Center).clickable(enabled = !isSpinning && !hasClaimedToday) { performSpin() }, shape = CircleShape, color = PrimaryYellow, shadowElevation = 8.dp, border = androidx.compose.foundation.BorderStroke(4.dp, Color.White)) {
                        Box(contentAlignment = Alignment.Center) { Text(stringResource(R.string.spin), color = BlackBackground, fontWeight = FontWeight.Black, fontSize = 14.sp) }
                    }
                }
                Spacer(modifier = Modifier.height(60.dp))
                Button(onClick = { performSpin() }, modifier = Modifier.fillMaxWidth().height(60.dp), shape = RoundedCornerShape(30.dp), colors = ButtonDefaults.buttonColors(containerColor = if (hasClaimedToday) Color.Gray else PrimaryYellow, disabledContainerColor = SurfaceColor), enabled = !isSpinning && !hasClaimedToday) {
                    Text(when { hasClaimedToday -> "CLAIMED TODAY"; isSpinning -> "SPINNING..."; else -> "SPIN NOW" }, color = if (hasClaimedToday) Color.White else BlackBackground, fontWeight = FontWeight.ExtraBold, fontSize = 20.sp)
                }
                Spacer(modifier = Modifier.height(24.dp))
                Text(if (hasClaimedToday) "You've already claimed your daily reward today!\nCome back tomorrow for another chance." else "Spin the wheel once daily for exciting rewards!", color = Color.Gray, fontSize = 14.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            }
        }
    }
}

@Composable
fun WheelHeader(onBack: () -> Unit, balance: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Back", tint = PrimaryYellow, modifier = Modifier.size(32.dp)) }
        Surface(color = SurfaceColor, shape = RoundedCornerShape(20.dp)) {
            Row(modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("₹", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.width(4.dp))
                Text(balance, color = Color.White, fontWeight = FontWeight.Bold)
            }
        }
    }
}
