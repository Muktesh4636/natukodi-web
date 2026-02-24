package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import androidx.compose.ui.res.stringResource
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
                    stringResource(R.string.refer_earn_title),
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
                        stringResource(R.string.invite_friends_win),
                        color = TextWhite,
                        fontSize = 28.sp,
                        fontWeight = FontWeight.ExtraBold
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
                            stringResource(R.string.your_referral_code),
                            color = TextGrey,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        val codeCopiedText = stringResource(R.string.code_copied)
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(BlackBackground.copy(alpha = 0.5f))
                                .padding(horizontal = 16.dp, vertical = 10.dp)
                                .clickable {
                                    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val clip = android.content.ClipData.newPlainText("Referral Code", referralCode)
                                    clipboard.setPrimaryClip(clip)
                                    android.widget.Toast.makeText(context, codeCopiedText, android.widget.Toast.LENGTH_SHORT).show()
                                }
                        ) {
                            Row(
                                modifier = Modifier
                                    .weight(1f)
                                    .horizontalScroll(rememberScrollState()),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = referralCode,
                                    color = PrimaryYellow,
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Black,
                                    letterSpacing = 1.sp,
                                    maxLines = 1
                                )
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                            Icon(Icons.Default.ContentCopy, null, tint = PrimaryYellow, modifier = Modifier.size(18.dp))
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
                                Text(stringResource(R.string.whatsapp), fontWeight = FontWeight.Bold)
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
                                Text(stringResource(R.string.share), color = BlackBackground, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                // Stats Section
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        StatCard(
                            title = stringResource(R.string.total_referrals),
                            value = "${referralData?.total_referrals ?: 0}",
                            icon = Icons.Filled.People,
                            modifier = Modifier.weight(1f)
                        )
                        StatCard(
                            title = stringResource(R.string.deposited_counts),
                            value = "${referralData?.active_referrals ?: 0}",
                            icon = Icons.Filled.CheckCircle,
                            modifier = Modifier.weight(1f),
                            color = GreenSuccess
                        )
                    }
                    StatCard(
                        title = stringResource(R.string.total_earned),
                        value = "₹${referralData?.total_earnings ?: "0"}",
                        icon = Icons.Filled.AccountBalanceWallet,
                        modifier = Modifier.fillMaxWidth(),
                        color = PrimaryYellow
                    )
                }

                // Milestone Section
                Text(
                    stringResource(R.string.milestone_bonuses),
                    color = TextWhite,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Black,
                    letterSpacing = 1.sp
                )
                Spacer(modifier = Modifier.height(16.dp))

                // Next Milestone
                referralData?.next_milestone?.let { next ->
                    val targetVal = next.target ?: next.next_milestone ?: 3
                    val nextRewardAmount = when (targetVal) {
                        3 -> 500
                        5, 8 -> 1000
                        10 -> 5000
                        20 -> 10000
                        30 -> 0  // Mega Spin uses next_bonus_display
                        50 -> 25000
                        100 -> 50000
                        else -> next.next_bonus.toInt()
                    }
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
                                    Text(stringResource(R.string.next_reward), color = TextGrey, fontSize = 12.sp)
                                    Text(
                                        text = next.next_bonus_display ?: "₹$nextRewardAmount",
                                        color = PrimaryYellow,
                                        fontSize = if (next.next_bonus_display != null) 18.sp else 24.sp,
                                        fontWeight = FontWeight.Black
                                    )
                                }
                                val current = next.current_progress
                                Box(contentAlignment = Alignment.Center) {
                                    CircularProgressIndicator(
                                        progress = { (next.progress_percentage / 100).toFloat().coerceIn(0f, 1f) },
                                        modifier = Modifier.size(60.dp),
                                        color = PrimaryYellow,
                                        trackColor = Color.DarkGray,
                                        strokeWidth = 6.dp
                                    )
                                    Text(
                                        "$current/$targetVal",
                                        color = TextWhite,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.height(12.dp))
                            val remaining = targetVal - next.current_progress
                            Text(
                                stringResource(R.string.refer_more_to_unlock, remaining),
                                color = TextWhite,
                                fontSize = 13.sp
                            )
                        }
                    }
                }

                // All Milestones List: 3 → ₹500, 5 more (8) → ₹1000, 10 → ₹5K, 20 → ₹10K, 30 → Mega Spin, 50 → ₹25K, 100 → ₹50K
                referralData?.milestones?.let { milestones ->
                    milestones.forEach { m ->
                        val displayBonus = when (m.count) {
                            3 -> 500
                            8 -> 1000
                            10 -> 5000
                            20 -> 10000
                            30 -> 0  // Mega Spin - uses bonus_display
                            50 -> 25000
                            100 -> 50000
                            else -> m.bonus
                        }
                        val (labelResId, labelFormatArgs) = when (m.count) {
                            8 -> R.string.five_more_referrals to emptyArray<Any>()
                            else -> R.string.referrals_count to arrayOf<Any>(m.count)
                        }
                        MilestoneCard(
                            count = m.count,
                            bonus = displayBonus,
                            bonusDisplay = m.bonus_display,
                            achieved = m.achieved,
                            progressCurrent = m.progress_current,
                            target = m.target,
                            labelResId = labelResId,
                            labelFormatArgs = labelFormatArgs
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))

                // My Referrals section - show 3 initially, View All to expand
                val referralsList = referralData?.referrals ?: emptyList()
                if (referralsList.isNotEmpty()) {
                    var showAllReferrals by remember { mutableStateOf(false) }
                    val displayedReferrals = if (showAllReferrals) referralsList else referralsList.take(3)
                    val hasMore = referralsList.size > 3

                    Text(
                        stringResource(R.string.my_referrals),
                        color = TextWhite,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = 1.sp
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        color = SurfaceColor
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            displayedReferrals.forEachIndexed { index, ref ->
                                ReferralListItem(
                                    username = ref.username,
                                    hasDeposit = ref.has_deposit
                                )
                                if (index < displayedReferrals.size - 1) {
                                    Spacer(modifier = Modifier.height(8.dp))
                                }
                            }
                            if (hasMore && !showAllReferrals) {
                                Spacer(modifier = Modifier.height(12.dp))
                                TextButton(
                                    onClick = { showAllReferrals = true },
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Text(stringResource(R.string.view_all_more, referralsList.size - 3), color = PrimaryYellow, fontWeight = FontWeight.Bold)
                                }
                            } else if (hasMore && showAllReferrals) {
                                Spacer(modifier = Modifier.height(12.dp))
                                TextButton(
                                    onClick = { showAllReferrals = false },
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Text(stringResource(R.string.view_less), color = PrimaryYellow, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(16.dp))
                }

                // How it works
                Text(
                    stringResource(R.string.how_it_works),
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
                        StepItem("1", stringResource(R.string.step_share_code))
                        StepDivider()
                        StepItem("2", stringResource(R.string.step_friend_deposits))
                        StepDivider()
                        StepItem("3", stringResource(R.string.step_get_bonus))
                        StepDivider()
                        StepItem("4", stringResource(R.string.step_milestone_bonuses))
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
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(32.dp)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    value,
                    color = TextWhite,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1
                )
            }
            Text(
                title,
                color = TextGrey,
                fontSize = 12.sp,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }
}

@Composable
fun MilestoneCard(
    count: Int,
    bonus: Int,
    bonusDisplay: String? = null,
    achieved: Boolean,
    progressCurrent: Int = 0,
    target: Int = count,
    labelResId: Int? = null,
    labelFormatArgs: Array<Any> = emptyArray(),
    label: String? = null
) {
    val resolvedLabel = when {
        labelResId != null -> if (labelFormatArgs.isEmpty()) stringResource(labelResId) else stringResource(labelResId, *labelFormatArgs)
        label != null -> label
        else -> "$count Referrals"
    }
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
                // Progress circle: X/3 or X/5
                val progress = if (target > 0) (progressCurrent.toFloat() / target).coerceIn(0f, 1f) else 0f
                Box(contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.size(44.dp),
                        color = if (achieved) PrimaryYellow else PrimaryYellow.copy(alpha = 0.6f),
                        trackColor = Color.DarkGray,
                        strokeWidth = 4.dp
                    )
                    if (achieved) {
                        Icon(
                            imageVector = Icons.Filled.Check,
                            contentDescription = null,
                            tint = BlackBackground,
                            modifier = Modifier.size(18.dp)
                        )
                    } else {
                        Text(
                            "$progressCurrent/$target",
                            color = TextWhite,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                Spacer(modifier = Modifier.width(16.dp))

                Column {
                    Text(
                        resolvedLabel,
                        color = if (achieved) PrimaryYellow else TextWhite,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        if (achieved) stringResource(R.string.achieved) else "$progressCurrent / $target",
                        color = TextGrey,
                        fontSize = 12.sp
                    )
                }
            }

            Text(
                text = bonusDisplay ?: "₹$bonus",
                color = if (achieved) PrimaryYellow else TextGrey,
                fontSize = if (bonusDisplay != null) 14.sp else 20.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun ReferralListItem(
    username: String,
    hasDeposit: Boolean
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(BlackBackground.copy(alpha = 0.5f))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(
                modifier = Modifier.size(36.dp),
                shape = CircleShape,
                color = PrimaryYellow.copy(alpha = 0.3f)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Filled.Person,
                        contentDescription = null,
                        tint = PrimaryYellow,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = username,
                color = TextWhite,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
        }
        if (hasDeposit) {
            Surface(
                shape = RoundedCornerShape(6.dp),
                color = GreenSuccess.copy(alpha = 0.3f)
            ) {
                Text(
                    stringResource(R.string.deposited),
                    color = GreenSuccess,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }
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
