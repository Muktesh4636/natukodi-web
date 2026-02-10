package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Hero Section
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 24.dp),
                shape = RoundedCornerShape(20.dp),
                color = SurfaceColor
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    // Icon
                    Surface(
                        modifier = Modifier.size(80.dp),
                        shape = CircleShape,
                        color = PrimaryYellow.copy(alpha = 0.2f)
                    ) {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Campaign,
                                contentDescription = null,
                                tint = PrimaryYellow,
                                modifier = Modifier.size(40.dp)
                            )
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    Text(
                        "Earn More, Refer More!",
                        color = TextWhite,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Text(
                        "Invite friends and unlock milestone bonuses",
                        color = TextGrey,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center
                    )
                }
            }
            
            // Statistics Cards
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                StatCard(
                    title = "Total Referrals",
                    value = "${referralData?.total_referrals ?: 0}",
                    icon = Icons.Filled.People,
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    title = "Active Referrals",
                    value = "${referralData?.active_referrals ?: 0}",
                    icon = Icons.Filled.CheckCircle,
                    modifier = Modifier.weight(1f),
                    color = GreenSuccess
                )
            }
            
            Spacer(modifier = Modifier.height(12.dp))
            
            // Total Earnings Card
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = SurfaceColor
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            "Total Earnings",
                            color = TextGrey,
                            fontSize = 14.sp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            "₹${referralData?.total_earnings ?: "0.00"}",
                            color = PrimaryYellow,
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Icon(
                        imageVector = Icons.Filled.AccountBalanceWallet,
                        contentDescription = null,
                        tint = PrimaryYellow,
                        modifier = Modifier.size(32.dp)
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Referral Code Section
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = SurfaceColor
            ) {
                Column(
                    modifier = Modifier.padding(20.dp)
                ) {
                    Text(
                        "Your Referral Code",
                        color = PrimaryYellow,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            referralCode,
                            color = TextWhite,
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.weight(1f)
                        )
                        IconButton(onClick = {
                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                            val clip = android.content.ClipData.newPlainText("Referral Code", referralCode)
                            clipboard.setPrimaryClip(clip)
                            android.widget.Toast.makeText(context, "Code copied!", android.widget.Toast.LENGTH_SHORT).show()
                        }) {
                            Icon(
                                imageVector = Icons.Filled.ContentCopy,
                                contentDescription = "Copy",
                                tint = PrimaryYellow,
                                modifier = Modifier.size(24.dp)
                            )
                        }
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Share Button
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
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF25D366)),
                shape = RoundedCornerShape(12.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        painter = painterResource(id = R.drawable.ic_whatsapp),
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Share on WhatsApp", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
            
            Spacer(modifier = Modifier.height(32.dp))
            
            // Milestone Progress Section
            Text(
                "Milestone Bonuses",
                color = TextWhite,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.fillMaxWidth()
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Text(
                "Earn bonus rewards when you reach referral milestones!",
                color = TextGrey,
                fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth()
            )
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Next Milestone Progress
            referralData?.next_milestone?.let { nextMilestone ->
                if (nextMilestone.next_milestone != null) {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        color = SurfaceColor
                    ) {
                        Column(
                            modifier = Modifier.padding(20.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    "Next Milestone",
                                    color = TextWhite,
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.Bold
                                )
                                Text(
                                    "₹${nextMilestone.next_bonus.toInt()}",
                                    color = PrimaryYellow,
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            
                            Spacer(modifier = Modifier.height(12.dp))
                            
                            Text(
                                "${nextMilestone.current_progress} / ${nextMilestone.next_milestone} referrals",
                                color = TextGrey,
                                fontSize = 14.sp
                            )
                            
                            Spacer(modifier = Modifier.height(8.dp))
                            
                            // Progress Bar
                            LinearProgressIndicator(
                                progress = { (nextMilestone.progress_percentage / 100).toFloat().coerceIn(0f, 1f) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(8.dp)
                                    .clip(RoundedCornerShape(4.dp)),
                                color = PrimaryYellow,
                                trackColor = SurfaceColor.copy(alpha = 0.3f)
                            )
                            
                            Spacer(modifier = Modifier.height(4.dp))
                            
                            Text(
                                "${nextMilestone.next_milestone!! - nextMilestone.current_progress} more referrals needed",
                                color = TextGrey,
                                fontSize = 12.sp
                            )
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(16.dp))
                }
            }
            
            // All Milestones List
            referralData?.milestones?.forEach { milestone ->
                MilestoneCard(
                    count = milestone.count,
                    bonus = milestone.bonus,
                    achieved = milestone.achieved,
                    currentReferrals = referralData?.total_referrals ?: 0
                )
                Spacer(modifier = Modifier.height(12.dp))
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Deposit-Based Bonus Rules
            Text(
                "Deposit Bonus Rules",
                color = TextWhite,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.fillMaxWidth()
            )
            
            Spacer(modifier = Modifier.height(12.dp))
            
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = SurfaceColor
            ) {
                Column(
                    modifier = Modifier.padding(20.dp)
                ) {
                    BonusRuleItem("₹100 Deposit", "₹100 Bonus")
                    BonusRuleItem("₹200 - ₹499 Deposit", "₹150 Bonus")
                    BonusRuleItem("₹500 - ₹999 Deposit", "₹300 Bonus")
                    BonusRuleItem("₹1000 - ₹4999 Deposit", "₹500 Bonus")
                    BonusRuleItem("₹5000+ Deposit", "₹1000 Bonus")
                }
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            Text(
                "💡 Tip: The more friends you refer, the more milestone bonuses you unlock!",
                color = TextGrey,
                fontSize = 14.sp,
                lineHeight = 20.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
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
