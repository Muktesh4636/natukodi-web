package com.sikwin.app.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import android.media.MediaPlayer
import com.sikwin.app.R
import com.sikwin.app.ui.theme.BlackBackground
import com.sikwin.app.ui.theme.PrimaryYellow
import com.sikwin.app.ui.theme.SurfaceColor
import kotlin.random.Random

@Composable
fun GuestSpinWheelDialog(
    onDismiss: () -> Unit,
    onRegisterClick: (Int) -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    var rotationAngle by remember { mutableStateOf(0f) }
    var isSpinning by remember { mutableStateOf(false) }
    var showResult by remember { mutableStateOf(false) }
    var wonAmount by remember { mutableIntStateOf(0) }

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

    val wheelItems = listOf(
        WheelItem("₹100", Color(0xFFFFD700)),
        WheelItem("₹10", Color(0xFF32CD32)),
        WheelItem("₹50", Color(0xFFFF4500)),
        WheelItem("₹20", Color(0xFF00CED1)),
        WheelItem("₹80", Color(0xFFFFA500)),
        WheelItem("₹30", Color(0xFF9370DB)),
        WheelItem("₹10", Color(0xFF32CD32)),
        WheelItem("₹20", Color(0xFF00CED1))
    )

    val rotation = animateFloatAsState(
        targetValue = rotationAngle,
        animationSpec = tween(
            durationMillis = 4000,
            easing = CubicBezierEasing(0.1f, 0.0f, 0.2f, 1f)
        ),
        label = "guest_wheel_rotation",
        finishedListener = {
            if (rotationAngle != 0f) {
                isSpinning = false
                showResult = true
            }
        }
    )

    fun performSpin() {
        if (!isSpinning && !showResult) {
            isSpinning = true
            val targetIndex = Random.nextInt(wheelItems.size)
            val amountStr = wheelItems[targetIndex].label.replace("₹", "")
            wonAmount = amountStr.toInt()

            val extraRotations = 8 + Random.nextInt(5)
            val degreesPerSegment = 360f / wheelItems.size
            val targetAngle = 270f - (targetIndex * degreesPerSegment) - (degreesPerSegment / 2)
            
            val currentRotation = rotationAngle % 360
            var angleDiff = targetAngle - currentRotation
            if (angleDiff <= 0) angleDiff += 360
            
            rotationAngle += (extraRotations * 360) + angleDiff
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = 0.8f)),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = Modifier
                    .width(340.dp)
                    .clip(RoundedCornerShape(24.dp))
                    .background(SurfaceColor)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "GUNDU ATA",
                        color = PrimaryYellow,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Black
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                if (!showResult) {
                    Text(
                        "Spin to win your first reward!",
                        color = Color.White,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    
                    Spacer(modifier = Modifier.height(24.dp))

                    // The Wheel
                    Box(
                        contentAlignment = Alignment.TopCenter,
                        modifier = Modifier.size(260.dp)
                    ) {
                        Box(modifier = Modifier.size(240.dp).align(Alignment.Center)) {
                            WheelCanvas(wheelItems, rotation.value)
                        }
                        Box(modifier = Modifier.padding(top = 0.dp)) {
                            WheelPointer()
                        }
                        Surface(
                            modifier = Modifier
                                .size(50.dp)
                                .align(Alignment.Center)
                                .clickable(enabled = !isSpinning) { performSpin() },
                            shape = CircleShape,
                            color = PrimaryYellow,
                            border = androidx.compose.foundation.BorderStroke(2.dp, Color.White)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(stringResource(R.string.spin), color = BlackBackground, fontWeight = FontWeight.Black, fontSize = 12.sp)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    Button(
                        onClick = { performSpin() },
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                        shape = RoundedCornerShape(25.dp),
                        enabled = !isSpinning
                    ) {
                        Text(if (isSpinning) "SPINNING..." else "SPIN NOW", color = BlackBackground, fontWeight = FontWeight.Bold)
                    }
                } else {
                    Text(
                        "CONGRATULATIONS!",
                        color = PrimaryYellow,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Black
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "You won ₹$wonAmount!",
                        color = Color.White,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        "Register now to claim your reward and start playing!",
                        color = Color.LightGray,
                        fontSize = 14.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    Button(
                        onClick = { onRegisterClick(wonAmount) },
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                        shape = RoundedCornerShape(25.dp)
                    ) {
                        Text(stringResource(R.string.claim_and_register), color = BlackBackground, fontWeight = FontWeight.Bold)
                    }
                    TextButton(onClick = onDismiss) {
                        Text(stringResource(R.string.maybe_later), color = Color.Gray)
                    }
                }
            }
        }
    }
}
