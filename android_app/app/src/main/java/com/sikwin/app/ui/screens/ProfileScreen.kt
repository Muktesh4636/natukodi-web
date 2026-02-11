package com.sikwin.app.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@Composable
fun ProfileScreen(
    viewModel: GunduAtaViewModel,
    onNavigate: (String) -> Unit
) {
    val context = LocalContext.current
    var showEditNameDialog by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf(viewModel.userProfile?.username ?: "") }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.checkSession()
                if (viewModel.loginSuccess) {
                    viewModel.fetchProfile()
                    viewModel.fetchWallet()
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    if (showEditNameDialog) {
        AlertDialog(
            onDismissRequest = { showEditNameDialog = false },
            title = { Text("Edit Name") },
            text = {
                OutlinedTextField(
                    value = newName,
                    onValueChange = { newName = it },
                    label = { Text("New Username") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            },
            confirmButton = {
                Button(onClick = {
                    if (newName.isNotBlank()) {
                        viewModel.updateUsername(newName)
                        showEditNameDialog = false
                    }
                }) {
                    Text("Save")
                }
            },
            dismissButton = {
                TextButton(onClick = { showEditNameDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        bottomBar = { HomeBottomNavigation(currentRoute = "me", onNavigate = onNavigate) },
        containerColor = BlackBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
        ) {
            // Profile Header
            ProfileHeader(
                username = viewModel.userProfile?.username ?: "User",
                balance = viewModel.wallet?.balance ?: "0.00",
                onWalletClick = { onNavigate("wallet") },
                onEditName = {
                    newName = viewModel.userProfile?.username ?: ""
                    showEditNameDialog = true
                },
                onRefreshBalance = { viewModel.fetchWallet() }
            )
            
            // Quick Actions Grid
            QuickActionsGrid(onNavigate)
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Menu Section 1
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(SurfaceColor)
            ) {
                ProfileMenuItem("Transaction record", Icons.AutoMirrored.Filled.List) { onNavigate("transactions") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Deposit record", Icons.Default.Description) { onNavigate("deposits_record") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Withdrawal record", Icons.Default.Receipt) { onNavigate("withdrawals_record") }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Menu Section 2
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(SurfaceColor)
            ) {
                ProfileMenuItem("My Withdrawal Account", Icons.Default.AccountBox) { onNavigate("withdrawal_account") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Personal data", Icons.Default.Person) { onNavigate("personal_info") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Security", Icons.Default.Security) { onNavigate("security") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Help center", Icons.Default.TipsAndUpdates) { onNavigate("help_center") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Refer a Friend", Icons.Default.PersonAdd) { onNavigate("affiliate") }
                Divider(color = BorderColor, thickness = 0.5.dp)
                ProfileMenuItem("Game Guidelines", Icons.Default.Casino) { onNavigate("game_guidelines") }
            }
            
            Spacer(modifier = Modifier.height(32.dp))
            
            // Logout Button
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
            ) {
                Button(
                    onClick = {
                        viewModel.logout()
                        // Clear Unity authentication data
                        viewModel.clearUnityAuthentication(context)
                        onNavigate("home")
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp),
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = SurfaceColor,
                        contentColor = Color.White
                    )
                ) {
                    Text(
                        text = "Log out",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(40.dp))
        }
    }
}

@Composable
fun ProfileHeader(
    username: String,
    balance: String,
    onWalletClick: () -> Unit,
    onEditName: () -> Unit,
    onRefreshBalance: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("My Dashboard", color = TextWhite, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.clickable { onWalletClick() }
            ) {
                Text("₹ $balance", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.width(8.dp))
                Icon(Icons.Default.AddBox, null, tint = PrimaryYellow)
            }
        }
        
        Spacer(modifier = Modifier.height(24.dp))
        
        Row(verticalAlignment = Alignment.CenterVertically) {
            // Static Default Avatar
            Box(
                modifier = Modifier
                    .size(80.dp)
                    .clip(CircleShape)
                    .background(Color.Gray),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Person, null, modifier = Modifier.size(50.dp), tint = TextWhite)
            }
            
            Spacer(modifier = Modifier.width(16.dp))
            
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Hi~ $username", color = TextWhite, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    IconButton(onClick = onEditName, modifier = Modifier.size(24.dp)) {
                        Icon(Icons.Default.Edit, "Edit Name", tint = PrimaryYellow, modifier = Modifier.size(16.dp))
                    }
                }
                Surface(
                    color = Color.DarkGray,
                    shape = RoundedCornerShape(4.dp),
                    modifier = Modifier.padding(top = 4.dp)
                ) {
                    Text(
                        "VIP0", 
                        color = Color.LightGray, 
                        fontSize = 10.sp, 
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
        }
        
        Spacer(modifier = Modifier.height(24.dp))
        
        Text("Total/INR", color = TextGrey, fontSize = 14.sp)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("₹", color = PrimaryYellow, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.width(8.dp))
            Text(balance, color = TextWhite, fontSize = 32.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.width(12.dp))

            // Animated refresh icon
            var rotationTarget by remember { mutableStateOf(0f) }
            val rotationAngle by animateFloatAsState(
                targetValue = rotationTarget,
                animationSpec = tween(durationMillis = 1000, easing = LinearEasing)
            )

            Box(
                modifier = Modifier
                    .clip(CircleShape)
                    .clickable {
                        rotationTarget += 360f
                        onRefreshBalance()
                    }
                    .padding(4.dp)
            ) {
                Icon(
                    Icons.Default.Refresh,
                    contentDescription = "Refresh Balance",
                    tint = PrimaryYellow,
                    modifier = Modifier
                        .size(20.dp)
                        .rotate(rotationAngle)
                )
            }
        }
    }
}

@Composable
fun QuickActionsGrid(onNavigate: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        val actions = listOf(
            QuickAction("My wallet", Icons.Default.AccountBalanceWallet, "wallet"),
            QuickAction("Withdrawal", Icons.Default.ArrowUpward, "withdraw"),
            QuickAction("Deposit", Icons.Default.ArrowDownward, "deposit")
        )
        
        actions.forEach { action ->
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(SurfaceColor)
                    .clickable { onNavigate(action.route) }
                    .padding(vertical = 16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Icon(action.icon, null, tint = PrimaryYellow, modifier = Modifier.size(28.dp))
                Spacer(modifier = Modifier.height(8.dp))
                Text(action.name, color = TextWhite, fontSize = 11.sp)
            }
        }
    }
}

data class QuickAction(val name: String, val icon: ImageVector, val route: String)

@Composable
fun ProfileMenuItem(text: String, icon: ImageVector, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = TextGrey, modifier = Modifier.size(24.dp))
        Spacer(modifier = Modifier.width(16.dp))
        Text(text, color = TextWhite, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Icon(Icons.Default.ArrowForward, null, tint = TextGrey)
    }
}


