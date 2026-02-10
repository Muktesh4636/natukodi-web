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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.nativeCanvas
import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalContext
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
import androidx.compose.runtime.DisposableEffect

@Composable
fun LuckyWheelScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
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
                isLooping = false // Play once, not loop
            }
        } catch (e: Exception) {
            android.util.Log.e("LuckyWheelScreen", "Error creating MediaPlayer", e)
            null
        }
    }
    
    // Release MediaPlayer when composable is disposed
    DisposableEffect(Unit) {
        onDispose {
            try {
                mediaPlayer?.release()
            } catch (e: Exception) {
                android.util.Log.e("LuckyWheelScreen", "Error releasing MediaPlayer", e)
            }
        }
    }
    
    // Play sound when wheel starts spinning
    LaunchedEffect(isSpinning) {
        if (isSpinning) {
            try {
                mediaPlayer?.let { player ->
                    if (player.isPlaying) {
                        player.seekTo(0)
                    } else {
                        player.start()
                    }
                }
            } catch (e: Exception) {
                // Handle error silently
                android.util.Log.e("LuckyWheelScreen", "Error playing sound", e)
            }
        }
    }

    // Check daily reward status when screen loads
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
        WheelItem("₹1000", Color(0xFFFF0000)), // Red
        WheelItem("₹500", Color(0xFFFF4500)),  // Orange Red
        WheelItem("₹100", Color(0xFFFFA500)),  // Orange
        WheelItem("₹20", Color(0xFFFFD700)),   // Gold
        WheelItem("₹10", Color(0xFF32CD32)),   // Lime Green
        WheelItem("₹5", Color(0xFF00CED1)),    // Dark Turquoise
        WheelItem("₹0", Color(0xFFC0C0C0))     // Silver
    )

    fun performSpin() {
        if (!isSpinning && !hasClaimedToday) {
            isSpinning = true

            // Call backend API to claim daily reward
            viewModel.claimDailyReward { success, amount, type, message ->
                if (success && amount != null) {
                    hasClaimedToday = true

                    // Find the index of the reward amount in wheel items
                    val targetIndex = when (amount) {
                        1000 -> 0
                        500 -> 1
                        100 -> 2
                        20 -> 3
                        10 -> 4
                        5 -> 5
                        else -> 6 // ₹0
                    }

                    lastResult = if (type == "MONEY") "₹$amount" else "₹0"

                    // Calculate spin animation
                    val extraRotations = 10 + Random.nextInt(5)
                    val degreesPerSegment = 360f / wheelItems.size
                    // The pointer is at the top (270 degrees in Canvas coordinates).
                    // When rotationAngle is 0, segment 0 starts at 0 degrees (right side).
                    // To bring segment 'targetIndex' to the top:
                    // targetAngle = 270 - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
                    val targetAngle = 270f - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
                    
                    // Ensure we always spin forward
                    val currentRotation = rotationAngle % 360
                    var angleDiff = targetAngle - currentRotation
                    if (angleDiff <= 0) angleDiff += 360
                    
                    rotationAngle += (extraRotations * 360) + angleDiff
                } else {
                    // On error, show a default result
                    val targetIndex = 6 // ₹0
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
            title = { Text("Result", fontWeight = FontWeight.Bold) },
            text = {
                val message = if (lastResult == "₹0") {
                    "Better luck next time! Try again tomorrow."
                } else {
                    "Congratulations! You won $lastResult"
                }
                Text(message)
            },
            confirmButton = {
                TextButton(onClick = { showResultDialog = false }) {
                    Text("OK", color = PrimaryYellow)
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
                    if (hasClaimedToday) "REWARD CLAIMED!" else "DAILY REWARDS",
                    color = Color.White,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.padding(bottom = 32.dp)
                )

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
                                enabled = !isSpinning && !hasClaimedToday,
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
                    onClick = { performSpin() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(60.dp),
                    shape = RoundedCornerShape(30.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (hasClaimedToday) Color.Gray else PrimaryYellow,
                        disabledContainerColor = SurfaceColor
                    ),
                    enabled = !isSpinning && !hasClaimedToday
                ) {
                    Text(
                        when {
                            hasClaimedToday -> "CLAIMED TODAY"
                            isSpinning -> "SPINNING..."
                            else -> "SPIN NOW"
                        },
                        color = if (hasClaimedToday) Color.White else BlackBackground,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 20.sp
                    )
                }

                Spacer(modifier = Modifier.height(24.dp))

                Text(
                    if (hasClaimedToday) {
                        "You've already claimed your daily reward today!\nCome back tomorrow for another chance."
                    } else {
                        "Spin the wheel once daily for exciting rewards!"
                    },
                    color = Color.Gray,
                    fontSize = 14.sp,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
            }
        }
    }
}

@Composable
fun WheelHeader(onBack: () -> Unit, balance: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Back", tint = PrimaryYellow, modifier = Modifier.size(32.dp))
        }
        
        Surface(
            color = SurfaceColor,
            shape = RoundedCornerShape(20.dp)
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("₹", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.width(4.dp))
                Text(balance, color = Color.White, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
fun WheelCanvas(items: List<WheelItem>, rotation: Float) {
    val density = LocalDensity.current
    val textPaint = remember {
        Paint().apply {
            color = android.graphics.Color.WHITE
            textAlign = Paint.Align.CENTER
            textSize = with(density) { 14.sp.toPx() }
            typeface = Typeface.DEFAULT_BOLD
        }
    }

    Canvas(
        modifier = Modifier
            .fillMaxSize()
            .rotate(rotation)
    ) {
        val sweepAngle = 360f / items.size
        val radius = size.minDimension / 2
        
        items.forEachIndexed { index, item ->
            val startAngle = index * sweepAngle
            
            drawArc(
                color = item.color,
                startAngle = startAngle,
                sweepAngle = sweepAngle,
                useCenter = true,
                size = Size(size.width, size.height)
            )
            
            // Draw text in the middle of the segment
            val angleInRadians = (startAngle + sweepAngle / 2) * (PI / 180f).toFloat()
            val textRadius = radius * 0.7f
            val x = (size.width / 2) + (textRadius * cos(angleInRadians))
            val y = (size.height / 2) + (textRadius * sin(angleInRadians))
            
            drawContext.canvas.nativeCanvas.apply {
                save()
                rotate(startAngle + sweepAngle / 2 + 90f, x, y)
                drawText(item.label, x, y, textPaint)
                restore()
            }

            // Outer Border for segments
            drawArc(
                color = Color.Black.copy(alpha = 0.3f),
                startAngle = startAngle,
                sweepAngle = sweepAngle,
                useCenter = true,
                style = Stroke(width = 2.dp.toPx())
            )
        }
        
        // Outer Rim
        drawCircle(
            color = Color.White,
            radius = radius,
            style = Stroke(width = 4.dp.toPx())
        )
    }
}

@Composable
fun WheelPointer() {
    Canvas(modifier = Modifier.size(40.dp)) {
        val path = androidx.compose.ui.graphics.Path().apply {
            moveTo(size.width / 2, 0f)
            lineTo(size.width / 2 - 15f, 30f)
            lineTo(size.width / 2 + 15f, 30f)
            close()
        }
        drawPath(path, color = Color.Red)
    }
}

data class WheelItem(val label: String, val color: Color)
