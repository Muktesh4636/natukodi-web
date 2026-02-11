package com.sikwin.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.graphics.Paint
import android.graphics.Typeface
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

data class WheelItem(val label: String, val color: Color)

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
                
                // Handle multi-line text (e.g., "Better luck\nnext time")
                val lines = item.label.split("\n")
                if (lines.size > 1) {
                    val lineHeight = textPaint.textSize * 1.2f
                    val totalHeight = lineHeight * lines.size
                    var currentY = y - (totalHeight / 2) + (textPaint.textSize / 2)
                    
                    lines.forEach { line ->
                        drawText(line, x, currentY, textPaint)
                        currentY += lineHeight
                    }
                } else {
                    drawText(item.label, x, y, textPaint)
                }
                
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
