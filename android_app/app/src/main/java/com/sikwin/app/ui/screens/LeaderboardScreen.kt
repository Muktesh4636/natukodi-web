package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LeaderboardScreen(viewModel: GunduAtaViewModel, onBack: () -> Unit) {
    
    LaunchedEffect(Unit) {
        viewModel.fetchLeaderboard()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Leaderboard", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = BlackBackground,
                    titleContentColor = TextWhite,
                    navigationIconContentColor = PrimaryYellow
                )
            )
        },
        containerColor = BlackBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            // User's Current Rank and Rotation
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                color = SurfaceColor,
                shape = RoundedCornerShape(16.dp),
                border = androidx.compose.foundation.BorderStroke(1.dp, PrimaryYellow.copy(alpha = 0.5f))
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "YOUR RANKING",
                            color = TextGrey,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            if (viewModel.userRank > 0) "#${viewModel.userRank}" else "Unranked",
                            color = PrimaryYellow,
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Black
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            "YOUR TURNOVER",
                            color = TextGrey,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            "₹${String.format("%.2f", viewModel.userRotationMoney)}",
                            color = TextWhite,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            // Prize Info Header
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 24.dp),
                color = SurfaceColor,
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        "DAILY CHAMPIONS",
                        color = PrimaryYellow,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = 2.sp
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "1st: ${viewModel.leaderboardPrizes["1st"]} | 2nd: ${viewModel.leaderboardPrizes["2nd"]} | 3rd: ${viewModel.leaderboardPrizes["3rd"]}",
                        color = TextWhite,
                        fontSize = 16.sp,
                        textAlign = TextAlign.Center,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "Turnover based prizes!",
                        color = TextGrey,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center
                    )
                    Text(
                        "Results will be announced daily 11:00 PM night",
                        color = TextGrey,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center
                    )
                }
            }

            if (viewModel.isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PrimaryYellow)
                }
            } else if (viewModel.leaderboardPlayers.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No data available yet", color = TextGrey)
                }
            } else {
                // Leaderboard List
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    itemsIndexed(viewModel.leaderboardPlayers) { _, playerMap ->
                        val rank = (playerMap["rank"] as? Double)?.toInt() ?: (playerMap["rank"] as? Int) ?: 0
                        val name = playerMap["username"] as? String ?: "Unknown"
                        val turnover = (playerMap["turnover"] as? Double) ?: (playerMap["turnover"] as? Int)?.toDouble() ?: 0.0
                        val prize = playerMap["prize"] as? String
                        
                        LeaderboardItem(rank, name, turnover, prize)
                    }
                }
            }
        }
    }
}

@Composable
fun LeaderboardItem(rank: Int, name: String, turnover: Double, prize: String?) {
    val isTopThree = rank <= 3
    val backgroundColor = when (rank) {
        1 -> Brush.horizontalGradient(listOf(Color(0xFFFFD700).copy(alpha = 0.2f), SurfaceColor))
        2 -> Brush.horizontalGradient(listOf(Color(0xFFC0C0C0).copy(alpha = 0.2f), SurfaceColor))
        3 -> Brush.horizontalGradient(listOf(Color(0xFFCD7F32).copy(alpha = 0.2f), SurfaceColor))
        else -> Brush.horizontalGradient(listOf(SurfaceColor, SurfaceColor))
    }

    val rankIconColor = when (rank) {
        1 -> Color(0xFFFFD700) // Gold
        2 -> Color(0xFFC0C0C0) // Silver
        3 -> Color(0xFFCD7F32) // Bronze
        else -> TextGrey
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = Color.Transparent
    ) {
        Row(
            modifier = Modifier
                .background(backgroundColor)
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Rank
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .clip(CircleShape)
                    .background(if (isTopThree) rankIconColor else Color.Transparent),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = rank.toString(),
                    color = if (isTopThree) BlackBackground else TextGrey,
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Player Info
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = name,
                    color = TextWhite,
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
                Text(
                    text = "Total Turnover: ₹${String.format("%.2f", turnover)}",
                    color = TextGrey,
                    fontSize = 14.sp
                )
            }

            // Prize for top 3
            if (prize != null) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "PRIZE",
                        color = rankIconColor,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black
                    )
                    Text(
                        text = prize,
                        color = PrimaryYellow,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 16.sp
                    )
                }
            }
        }
    }
}
