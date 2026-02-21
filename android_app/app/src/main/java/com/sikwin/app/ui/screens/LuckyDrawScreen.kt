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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.nativeCanvas
import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import com.sikwin.app.R
import com.sikwin.app.ui.theme.BlackBackground
import com.sikwin.app.ui.theme.PrimaryYellow
import com.sikwin.app.ui.theme.SurfaceColor
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.random.Random

import android.media.MediaPlayer

@Composable
fun LuckyDrawScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onNavigate: (String) -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    var rotationAngle by remember { mutableStateOf(0f) }
    var isSpinning by remember { mutableStateOf(false) }
    var showResultDialog by remember { mutableStateOf(false) }
    var lastResult by remember { mutableStateOf("") }
    var hasClaimed by remember { mutableStateOf(false) }
    var claimedAmount by remember { mutableStateOf<String?>(null) }
    var eligibleAmount by remember { mutableStateOf<Double?>(null) }

    // MediaPlayer for wheel sound
    val mediaPlayer = remember {
        try {
            MediaPlayer.create(context, com.sikwin.app.R.raw.wheel_sound)?.apply {
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

    // Check lucky draw status when screen loads
    LaunchedEffect(Unit) {
        viewModel.checkLuckyDrawStatus { claimed, message, amount, depositAmount ->
            hasClaimed = claimed
            claimedAmount = amount
            eligibleAmount = depositAmount
            if (claimed && amount != null) {
                lastResult = "₹$amount"
            }
        }
    }

    // Lucky Draw prizes: 100, 300, 500, 1000, 5000, 10000
    val wheelItems = listOf(
        WheelItem("₹10000", Color(0xFFFF0000)), // Red
        WheelItem("₹5000", Color(0xFFFF4500)),  // Orange Red
        WheelItem("₹1000", Color(0xFFFFA500)),  // Orange
        WheelItem("₹500", Color(0xFFFFD700)),   // Gold
        WheelItem("₹300", Color(0xFF32CD32)),   // Lime Green
        WheelItem("₹100", Color(0xFF00CED1))    // Dark Turquoise
    )

    fun performSpin() {
        if (!isSpinning && !hasClaimed && eligibleAmount != null && eligibleAmount!! > 0) {
            isSpinning = true

            // Call backend API to claim lucky draw
            viewModel.claimLuckyDraw { success, amount, message ->
                if (success && amount != null) {
                    hasClaimed = true

                    // Find the index of the reward amount in wheel items
                    val targetIndex = when (amount) {
                        10000 -> 0
                        5000 -> 1
                        1000 -> 2
                        500 -> 3
                        300 -> 4
                        100 -> 5
                        else -> 0 // Default to first
                    }

                    lastResult = "₹$amount"

                    // Refresh wallet balance after successful claim
                    viewModel.fetchWallet()

                    // Calculate spin animation
                    val extraRotations = 10 + Random.nextInt(5)
                    val degreesPerSegment = 360f / wheelItems.size
                    val targetAngle = 270f - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
                    
                    val currentRotation = rotationAngle % 360
                    var angleDiff = targetAngle - currentRotation
                    if (angleDiff <= 0) angleDiff += 360
                    
                    rotationAngle += (extraRotations * 360) + angleDiff
                } else {
                    // On error, show a default result
                    val targetIndex = 0
                    lastResult = "₹0"

                    val extraRotations = 10 + Random.nextInt(5)
                    val degreesPerSegment = 360f / wheelItems.size
                    val targetAngle = 270f - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
                    
                    val currentRotation = rotationAngle % 360
                    var angleDiff = targetAngle - currentRotation
                    if (angleDiff <= 0) angleDiff += 360
                    
                    rotationAngle += (extraRotations * 360) + angleDiff

                    // Show error message
                    if (message != null) {
                        // You could show a toast or dialog here
                    }
                }
            }
        }
    }

    val rotation = animateFloatAsState(
        targetValue = rotationAngle,
        animationSpec = tween(
            durationMillis = 4000,
            easing = CubicBezierEasing(0.1f, 0.0f, 0.2f, 1f)
        ),
        label = "wheel_rotation",
        finishedListener = {
            if (rotationAngle != 0f) {
                isSpinning = false
                showResultDialog = true
            }
        }
    )

    if (showResultDialog) {
        AlertDialog(
            onDismissRequest = { showResultDialog = false },
            title = { Text(stringResource(R.string.lucky_draw_result), fontWeight = FontWeight.Bold) },
            text = {
                val message = if (lastResult == "₹0") {
                    "Better luck next time! Make a deposit to try again."
                } else {
                    "Congratulations! You won $lastResult"
                }
                Text(message)
            },
            confirmButton = {
                TextButton(onClick = { showResultDialog = false }) {
                    Text(stringResource(R.string.ok), color = PrimaryYellow)
                }
            },
            containerColor = SurfaceColor,
            titleContentColor = PrimaryYellow,
            textContentColor = Color.White
        )
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        // Decorative Background Money
        Image(
            painter = painterResource(id = R.drawable.money_decoration),
            contentDescription = null,
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp),
            contentScale = ContentScale.Inside,
            alpha = 0.4f
        )
        
        Column(modifier = Modifier.fillMaxSize()) {
            WheelHeader(onBack, viewModel.wallet?.balance ?: "0.00")
            
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(
                    if (hasClaimed) "LUCKY DRAW CLAIMED!" else "LUCKY DRAW",
                    color = Color.White,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.padding(bottom = 16.dp)
                )
                
                if (eligibleAmount != null && eligibleAmount!! > 0) {
                    Text(
                        "Based on your deposit of ₹${eligibleAmount!!.toInt()}",
                        color = PrimaryYellow,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 16.dp)
                    )
                } else {
                    Text(
                        "Make a bank transfer deposit to spin!",
                        color = Color.Gray,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(bottom = 16.dp)
                    )
                }

                // The Wheel Container
                Box(
                    contentAlignment = Alignment.TopCenter,
                    modifier = Modifier.size(360.dp)
                ) {
                    // Outer Glow/Ring
                    Canvas(modifier = Modifier.size(340.dp).align(Alignment.Center)) {
                        drawCircle(
                            color = PrimaryYellow.copy(alpha = 0.2f),
                            radius = size.minDimension / 2,
                            style = Stroke(width = 20.dp.toPx())
                        )
                    }

                    // The Wheel
                    Box(modifier = Modifier.size(300.dp).align(Alignment.Center)) {
                         WheelCanvas(wheelItems, rotation.value)
                    }

                    // The Pointer (At the top)
                    Box(modifier = Modifier.padding(top = 10.dp)) {
                         WheelPointer()
                    }
                    
                    // Center Hub
                    Surface(
                        modifier = Modifier
                            .size(60.dp)
                            .align(Alignment.Center)
                            .clickable(
                                enabled = !isSpinning && !hasClaimed && eligibleAmount != null && eligibleAmount!! > 0,
                                onClick = { performSpin() }
                            ),
                        shape = CircleShape,
                        color = PrimaryYellow,
                        shadowElevation = 8.dp,
                        border = androidx.compose.foundation.BorderStroke(4.dp, Color.White)
                    ) {
                         Box(contentAlignment = Alignment.Center) {
                             Text(
                                 "SPIN", 
                                 color = BlackBackground, 
                                 fontWeight = FontWeight.Black, 
                                 fontSize = 14.sp
                             )
                         }
                    }
                }

                Spacer(modifier = Modifier.height(60.dp))

                // Spin Button
                Button(
                    onClick = { 
                        if (hasClaimed || eligibleAmount == null || eligibleAmount!! <= 0) {
                            onNavigate("deposit")
                        } else {
                            performSpin()
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(60.dp),
                    shape = RoundedCornerShape(30.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (hasClaimed || eligibleAmount == null || eligibleAmount!! <= 0) Color.Gray else PrimaryYellow,
                        disabledContainerColor = SurfaceColor
                    ),
                    enabled = !isSpinning
                ) {
                    Text(
                        when {
                            hasClaimed -> "MAKE A DEPOSIT"
                            eligibleAmount == null || eligibleAmount!! <= 0 -> "MAKE A DEPOSIT"
                            isSpinning -> "SPINNING..."
                            else -> "SPIN NOW"
                        },
                        color = if (hasClaimed || eligibleAmount == null || eligibleAmount!! <= 0) Color.White else BlackBackground,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 20.sp
                    )
                }

                Spacer(modifier = Modifier.height(24.dp))

                Text(
                    if (hasClaimed) {
                        "You've already claimed your lucky draw reward!\nMake another deposit to try again."
                    } else if (eligibleAmount == null || eligibleAmount!! <= 0) {
                        "Make a bank transfer deposit to unlock the lucky draw spin!"
                    } else {
                        "Spin the wheel for exciting rewards based on your deposit!"
                    },
                    color = Color.Gray,
                    fontSize = 14.sp,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
            }
        }
    }
}
