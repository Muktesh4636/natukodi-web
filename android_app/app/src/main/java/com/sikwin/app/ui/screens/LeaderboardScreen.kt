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

data class LeaderboardPlayer(
    val name: String,
    val winnings: String,
    val prize: String? = null
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LeaderboardScreen(viewModel: GunduAtaViewModel, onBack: () -> Unit) {
    val currentUserName = viewModel.userProfile?.username ?: "You"
    val currentUserRotation = "₹${String.format("%.2f", viewModel.userRotationMoney)}"
    val currentUserRank = viewModel.userRank

    // Base leaderboard players
    val basePlayers = listOf(
        LeaderboardPlayer("Muktesh", "₹1,25,000", "₹1,000"),
        LeaderboardPlayer("Sai Krishna", "₹98,500", "₹500"),
        LeaderboardPlayer("Mahesh", "₹85,200", "₹100"),
        LeaderboardPlayer("Rahul", "₹72,000"),
        LeaderboardPlayer("Priya", "₹65,400"),
        LeaderboardPlayer("Vikram", "₹58,900"),
        LeaderboardPlayer("Anjali", "₹52,100"),
        LeaderboardPlayer("Suresh", "₹48,300"),
        LeaderboardPlayer("Kiran", "₹42,700"),
        LeaderboardPlayer("Deepak", "₹38,500")
    )

    // Create a dynamic list that includes the current user if they are ranked
    val dynamicPlayers = remember(currentUserRank, viewModel.userRotationMoney) {
        val list = basePlayers.toMutableList()
        
        // If user is ranked
        if (currentUserRank > 0) {
            val userEntry = LeaderboardPlayer(
                name = "$currentUserName (You)",
                winnings = currentUserRotation,
                prize = when(currentUserRank) {
                    1 -> "₹1,000"; 2 -> "₹500"; 3 -> "₹100"; else -> null
                }
            )
            
            if (currentUserRank <= 10) {
                // Replace the entry at that rank (0-indexed)
                if (currentUserRank - 1 < list.size) {
                    list[currentUserRank - 1] = userEntry
                }
            } else {
                // Add as an 11th entry if rank is > 10
                list.add(userEntry)
            }
        }
        list
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
                            "ROTATION MONEY",
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
                        "1st: ₹1000 | 2nd: ₹500 | 3rd: ₹100",
                        color = TextWhite,
                        fontSize = 16.sp,
                        textAlign = TextAlign.Center,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "Daily rewards paid every 24 hours!",
                        color = TextGrey,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center
                    )
                }
            }

            // Leaderboard List
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                itemsIndexed(dynamicPlayers) { index, player ->
                    val rankToShow = if (index < 10) index + 1 else currentUserRank
                    LeaderboardItem(rankToShow, player)
                }
            }
        }
    }
}

@Composable
fun LeaderboardItem(rank: Int, player: LeaderboardPlayer) {
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
                    text = player.name,
                    color = TextWhite,
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp
                )
                Text(
                    text = "Total Winnings: ${player.winnings}",
                    color = TextGrey,
                    fontSize = 14.sp
                )
            }

            // Prize for top 3
            if (player.prize != null) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "PRIZE",
                        color = rankIconColor,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black
                    )
                    Text(
                        text = player.prize,
                        color = PrimaryYellow,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 16.sp
                    )
                }
            }
        }
    }
}
