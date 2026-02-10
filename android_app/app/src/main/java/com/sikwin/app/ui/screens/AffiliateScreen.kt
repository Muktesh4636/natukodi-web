package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Campaign
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.IconButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AffiliateScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        TopAppBar(
            title = {
                Text(
                    "Affiliate marketing",
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
            colors = androidx.compose.material3.TopAppBarDefaults.smallTopAppBarColors(
                containerColor = BlackBackground
            )
        )
        Spacer(modifier = Modifier.height(24.dp))
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Surface(
                modifier = Modifier
                    .size(100.dp),
                shape = CircleShape,
                color = SurfaceColor
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
                "Earn with Gundu Ata",
                color = TextWhite,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                "Share your referral code with friends. Whenever someone signs up with your code and deposits, you earn a bonus based on their deposit amount.",
                color = TextGrey,
                fontSize = 16.sp,
                lineHeight = 22.sp
            )
            Spacer(modifier = Modifier.height(24.dp))
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(SurfaceColor, shape = RoundedCornerShape(12.dp))
                    .padding(16.dp),
                shape = RoundedCornerShape(12.dp),
                color = SurfaceColor
            ) {
                Column {
                    Text("Your referral code", color = PrimaryYellow, fontSize = 14.sp)
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(viewModel.userProfile?.referral_code ?: "ABC123", color = TextWhite, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                        IconButton(onClick = {
                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                            val clip = android.content.ClipData.newPlainText("Referral Code", viewModel.userProfile?.referral_code ?: "")
                            clipboard.setPrimaryClip(clip)
                            android.widget.Toast.makeText(context, "Code copied!", android.widget.Toast.LENGTH_SHORT).show()
                        }) {
                            Icon(imageVector = Icons.Filled.ContentCopy, contentDescription = null, tint = PrimaryYellow)
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
            
            // WhatsApp Share Button
            Button(
                onClick = {
                    val referralCode = viewModel.userProfile?.referral_code ?: ""
                    val shareMessage = "Join me on Gundu Ata and win big! Use my referral code: $referralCode\n\nDownload now: https://gunduata.com/signup?ref=$referralCode"
                    val intent = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_TEXT, shareMessage)
                        setPackage("com.whatsapp")
                    }
                    try {
                        context.startActivity(intent)
                    } catch (e: Exception) {
                        // If WhatsApp is not installed, show generic share sheet
                        val genericIntent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, shareMessage)
                        }
                        context.startActivity(Intent.createChooser(genericIntent, "Share via"))
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
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
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Bonus Rules Section
            Text(
                "Bonus Rules:",
                color = TextWhite,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(12.dp))
            BonusRuleItem("₹100 Deposit", "₹100 Bonus")
            BonusRuleItem("₹200 - ₹499 Deposit", "₹150 Bonus")
            BonusRuleItem("₹500 - ₹999 Deposit", "₹300 Bonus")
            BonusRuleItem("₹1000 - ₹4999 Deposit", "₹500 Bonus")
            BonusRuleItem("₹5000+ Deposit", "₹1000 Bonus")
            
            Spacer(modifier = Modifier.height(24.dp))
            Text(
                "Need promotional banners or tips? Contact our support and we’ll help you grow your audience.",
                color = TextGrey,
                fontSize = 14.sp,
                lineHeight = 20.sp,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )
        }
    }
}

@Composable
fun BonusRuleItem(tier: String, bonus: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(tier, color = TextGrey, fontSize = 14.sp)
        Text(bonus, color = PrimaryYellow, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}
