package com.sikwin.app.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WalletScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit,
    onNavigateToDeposit: () -> Unit,
    onNavigateToWithdraw: () -> Unit
) {
    LaunchedEffect(Unit) {
        viewModel.fetchWallet()
    }

    val balance = viewModel.wallet?.balance ?: "0.00"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF1A1A1A)) // Dark background like in image
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
                    tint = Color(0xFFDAA520), // Golden color for back arrow
                    modifier = Modifier.size(24.dp)
                )
            }
            Text(
                stringResource(R.string.my_wallet),
                color = Color(0xFFDAA520), // Golden color for title
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.width(48.dp)) // To balance the back button
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp)
        ) {
            // Total Balance Card (Gold/Yellow)
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(140.dp)
                    .clip(RoundedCornerShape(24.dp)),
                color = Color(0xFFE6B84D) // Gold background
            ) {
                Box(modifier = Modifier.fillMaxSize()) {
                    // Wallet icon background placeholder
                    Icon(
                        Icons.Default.AccountBalanceWallet,
                        contentDescription = null,
                        tint = Color.White.copy(alpha = 0.2f),
                        modifier = Modifier
                            .size(100.dp)
                            .align(Alignment.TopEnd)
                            .padding(end = 16.dp, top = 8.dp)
                    )
                    
                    Column(
                        modifier = Modifier
                            .padding(20.dp)
                            .fillMaxSize(),
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            stringResource(R.string.total_inr),
                            color = Color.DarkGray,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "₹$balance",
                                color = Color.Black,
                                fontSize = 36.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            val rotation = remember { androidx.compose.animation.core.Animatable(0f) }
                            val scope = rememberCoroutineScope()

                            IconButton(onClick = {
                                scope.launch {
                                    rotation.animateTo(
                                        targetValue = rotation.value + 360f,
                                        animationSpec = androidx.compose.animation.core.tween(durationMillis = 600)
                                    )
                                }
                                viewModel.fetchWallet()
                            }) {
                                Icon(
                                    Icons.Default.Refresh,
                                    contentDescription = "Refresh",
                                    tint = Color.Black,
                                    modifier = Modifier
                                        .size(28.dp)
                                        .graphicsLayer {
                                            rotationZ = rotation.value
                                        }
                                )
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Main Wallet Card
            WalletCard(
                title = stringResource(R.string.main_wallet),
                amount = balance,
                icon = Icons.Default.AccountBalanceWallet,
                actions = {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        WalletActionButton(
                            text = stringResource(R.string.withdrawal),
                            icon = Icons.Default.VerticalAlignBottom,
                            onClick = onNavigateToWithdraw
                        )
                        Divider(
                            modifier = Modifier.height(24.dp).width(1.dp),
                            color = Color.LightGray
                        )
                        WalletActionButton(
                            text = stringResource(R.string.deposit),
                            icon = Icons.Default.VerticalAlignTop,
                            onClick = onNavigateToDeposit
                        )
                    }
                }
            )
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
fun WalletCard(
    title: String,
    amount: String,
    icon: ImageVector,
    actions: @Composable () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp)),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF0F0F0)) // Light grey/white card
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            // Subtle wave/line pattern simulation
            // (Skipped complex graphics for now, focusing on layout)
            
            Column(
                modifier = Modifier.padding(24.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        title,
                        color = Color.Black,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Icon(
                        icon,
                        contentDescription = null,
                        tint = Color.DarkGray,
                        modifier = Modifier.size(48.dp)
                    )
                }
                
                Spacer(modifier = Modifier.height(24.dp))
                
                Text(
                    "₹$amount",
                    color = Color.Black,
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold
                )
                
                Spacer(modifier = Modifier.height(16.dp))
                Divider(color = Color.LightGray, thickness = 0.5.dp)
                
                actions()
            }
        }
    }
}

@Composable
fun WalletActionButton(
    text: String,
    icon: ImageVector,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .clickable { onClick() }
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = Color.Black,
            modifier = Modifier.size(20.dp)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text,
            color = Color.Black,
            fontSize = 16.sp,
            fontWeight = FontWeight.Medium
        )
    }
}
