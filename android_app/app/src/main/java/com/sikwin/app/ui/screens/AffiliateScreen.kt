package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.BorderStroke
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import android.content.Context
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.sikwin.app.R
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sikwin.app.ui.theme.*
import android.content.Intent
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.ui.text.style.TextAlign
import kotlin.math.min

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AffiliateScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    
    // Fetch referral data
    LaunchedEffect(Unit) {
        viewModel.fetchReferralData()
        if (viewModel.userProfile == null || viewModel.userProfile?.referral_code == null) {
            viewModel.fetchProfile()
        }
    }
    
    val referralData = viewModel.referralData
    val referralCode = referralData?.referral_code ?: viewModel.userProfile?.referral_code ?: "ABC123"
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        TopAppBar(
            title = {
                Text(
                    "Refer & Earn",
                    color = TextWhite,
                    fontWeight = FontWeight.Bold,
                    fontSize = 20.sp
                )
            },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Back",
                        tint = TextWhite
                    )
                }
            },
            colors = androidx.compose.material3.TopAppBarDefaults.topAppBarColors(
                containerColor = BlackBackground
            )
        )
        
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
        ) {
            // New Stylish Hero Section with Gradient
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp)
                    .background(
                        brush = Brush.verticalGradient(
                            colors = listOf(PrimaryYellow.copy(alpha = 0.3f), BlackBackground)
                        )
                    ),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        imageVector = Icons.Filled.CardGiftcard,
                        contentDescription = null,
                        tint = PrimaryYellow,
                        modifier = Modifier.size(80.dp)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        "Invite Friends & Win!",
                        color = TextWhite,
                        fontSize = 28.sp,
                        fontWeight = FontWeight.ExtraBold
                    )
                    Text(
                        "Earn up to ₹10,000 for every friend",
                        color = PrimaryYellow,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
            }

            Column(modifier = Modifier.padding(horizontal = 16.dp)) {
                // Stylish Referral Code Card
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .offset(y = (-30).dp),
                    shape = RoundedCornerShape(16.dp),
                    color = SurfaceColor,
                    shadowElevation = 8.dp
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            "YOUR REFERRAL CODE",
                            color = TextGrey,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center,
                            modifier = Modifier
                                .wrapContentWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(BlackBackground.copy(alpha = 0.5f))
                                .padding(horizontal = 24.dp, vertical = 12.dp)
                                .clickable {
                                    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val clip = android.content.ClipData.newPlainText("Referral Code", referralCode)
                                    clipboard.setPrimaryClip(clip)
                                    android.widget.Toast.makeText(context, "Code copied!", android.widget.Toast.LENGTH_SHORT).show()
                                }
                        ) {
                            Text(
                                text = referralCode,
                                color = PrimaryYellow,
                                fontSize = 32.sp,
                                fontWeight = FontWeight.Black,
                                letterSpacing = 2.sp,
                                maxLines = 1
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            Icon(Icons.Default.ContentCopy, null, tint = PrimaryYellow, modifier = Modifier.size(20.dp))
                        }
                        
                        Spacer(modifier = Modifier.height(20.dp))
                        
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Button(
                                onClick = {
                                    val shareMessage = "🎲 Join me on Gundu Ata and win big!\n\nUse my referral code: $referralCode\n\nDownload now: https://gunduata.com/signup?ref=$referralCode"
                                    val intent = Intent(Intent.ACTION_SEND).apply {
                                        type = "text/plain"
                                        putExtra(Intent.EXTRA_TEXT, shareMessage)
                                        setPackage("com.whatsapp")
                                    }
                                    try {
                                        context.startActivity(intent)
                                    } catch (e: Exception) {
                                        val genericIntent = Intent(Intent.ACTION_SEND).apply {
                                            type = "text/plain"
                                            putExtra(Intent.EXTRA_TEXT, shareMessage)
                                        }
                                        context.startActivity(Intent.createChooser(genericIntent, "Share via"))
                                    }
                                },
                                modifier = Modifier.weight(1f).height(50.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF25D366)),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Icon(painterResource(id = R.drawable.ic_whatsapp), null, tint = Color.White, modifier = Modifier.size(20.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("WhatsApp", fontWeight = FontWeight.Bold)
                            }
                            
                            Button(
                                onClick = {
                                    val shareMessage = "🎲 Join me on Gundu Ata and win big!\n\nUse my referral code: $referralCode\n\nDownload now: https://gunduata.com/signup?ref=$referralCode"
                                    val genericIntent = Intent(Intent.ACTION_SEND).apply {
                                        type = "text/plain"
                                        putExtra(Intent.EXTRA_TEXT, shareMessage)
                                    }
                                    context.startActivity(Intent.createChooser(genericIntent, "Share via"))
                                },
                                modifier = Modifier.weight(1f).height(50.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Icon(Icons.Default.Share, null, tint = BlackBackground, modifier = Modifier.size(20.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Share", color = BlackBackground, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                // Stats Section
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 24.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    StatCard(
                        title = "Total Referrals",
                        value = "${referralData?.total_referrals ?: 0}",
                        icon = Icons.Filled.People,
                        modifier = Modifier.weight(1f)
                    )
                    StatCard(
                        title = "Total Earned",
                        value = "₹${referralData?.total_earnings ?: "0"}",
                        icon = Icons.Filled.AccountBalanceWallet,
                        modifier = Modifier.weight(1f),
                        color = GreenSuccess
                    )
                }

                // Milestone Section
                Text(
                    "MILESTONE BONUSES",
                    color = TextWhite,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Black,
                    letterSpacing = 1.sp
                )
                Spacer(modifier = Modifier.height(16.dp))

                // Next Milestone
                referralData?.next_milestone?.let { next ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = SurfaceColor,
                        border = BorderStroke(1.dp, PrimaryYellow.copy(alpha = 0.5f))
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column {
                                    Text("Next Reward", color = TextGrey, fontSize = 12.sp)
                                    Text("₹${next.next_bonus.toInt()}", color = PrimaryYellow, fontSize = 24.sp, fontWeight = FontWeight.Black)
                                }
                                Box(contentAlignment = Alignment.Center) {
                                    CircularProgressIndicator(
                                        progress = { (next.progress_percentage / 100).toFloat().coerceIn(0f, 1f) },
                                        modifier = Modifier.size(60.dp),
                                        color = PrimaryYellow,
                                        trackColor = Color.DarkGray,
                                        strokeWidth = 6.dp
                                    )
                                    Text(
                                        "${next.progress_percentage.toInt()}%",
                                        color = TextWhite,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                "Refer ${next.next_milestone!! - next.current_progress} more friends to unlock!",
                                color = TextWhite,
                                fontSize = 13.sp
                            )
                        }
                    }
                }

                // How it works
                Text(
                    "HOW IT WORKS",
                    color = TextWhite,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Black,
                    letterSpacing = 1.sp
                )
                Spacer(modifier = Modifier.height(16.dp))
                
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 32.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = SurfaceColor
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        StepItem("1", "Share your code with friends")
                        StepDivider()
                        StepItem("2", "Friend registers & deposits ₹100+")
                        StepDivider()
                        StepItem("3", "You get ₹100 instantly!")
                        StepDivider()
                        StepItem("4", "Unlock massive milestone bonuses")
                    }
                }
            }
        }
    }
}

@Composable
fun StepItem(number: String, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            modifier = Modifier.size(28.dp),
            shape = CircleShape,
            color = PrimaryYellow
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(number, color = BlackBackground, fontWeight = FontWeight.Bold, fontSize = 14.sp)
            }
        }
        Spacer(modifier = Modifier.width(16.dp))
        Text(text, color = TextWhite, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun StepDivider() {
    Box(
        modifier = Modifier
            .padding(start = 13.dp)
            .width(2.dp)
            .height(20.dp)
            .background(PrimaryYellow.copy(alpha = 0.3f))
    )
}

@Composable
fun StatCard(
    title: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier = Modifier,
    color: Color = PrimaryYellow
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = SurfaceColor
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(32.dp)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                value,
                color = TextWhite,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Text(
                title,
                color = TextGrey,
                fontSize = 12.sp
            )
        }
    }
}

@Composable
fun MilestoneCard(
    count: Int,
    bonus: Int,
    achieved: Boolean,
    currentReferrals: Int
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = if (achieved) PrimaryYellow.copy(alpha = 0.1f) else SurfaceColor,
        border = androidx.compose.foundation.BorderStroke(
            width = if (achieved) 2.dp else 1.dp,
            color = if (achieved) PrimaryYellow else BorderColor
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f)
            ) {
                // Checkmark or Number Icon
                Surface(
                    modifier = Modifier.size(40.dp),
                    shape = CircleShape,
                    color = if (achieved) PrimaryYellow else SurfaceColor.copy(alpha = 0.5f)
                ) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        if (achieved) {
                            Icon(
                                imageVector = Icons.Filled.Check,
                                contentDescription = null,
                                tint = BlackBackground,
                                modifier = Modifier.size(20.dp)
                            )
                        } else {
                            Text(
                                "$count",
                                color = TextGrey,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
                
                Spacer(modifier = Modifier.width(16.dp))
                
                Column {
                    Text(
                        "$count Referrals",
                        color = if (achieved) PrimaryYellow else TextWhite,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        if (achieved) "Achieved!" else "${min(count, currentReferrals)} / $count",
                        color = TextGrey,
                        fontSize = 12.sp
                    )
                }
            }
            
            Text(
                "₹$bonus",
                color = if (achieved) PrimaryYellow else TextGrey,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun BonusRuleItem(tier: String, bonus: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(tier, color = TextGrey, fontSize = 14.sp)
        Text(bonus, color = PrimaryYellow, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}
